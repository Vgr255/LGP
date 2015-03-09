﻿# the first 12 bytes are the file creator
# then a 4-bytes integer about the number of files

# Table of Contents; each entry is like this:
# sequence of null-terminated 20-bytes-long string; filename
# 4-bytes giving the starting offset of each file
# 1 byte of apparently unused data
# 2 bytes saying the number of conflicts

# after that, the conflicts table, according to Aali
# compare the end of the ToC against the beginning of the first file to get it

# Conflicts explained, courtesy of Aali:
# the last 2 bytes of each ToC entry state the amount of conflicts
# for each of those there are 2 other bytes that tell you
# how many subdirectories there are for each conflict;
# and THEN, we need to read a 128-byte string (the name of the subdirectory)
# then there are two bytes that tell us the ToC index it corresponds to

# HUGE thanks to Andy_S of EsperNet, who helped me through this headache
# I have never really messed around with file formats before, so I had nothing
# he helped me find my way through this and make it work as it should

import threading
import hashlib
import time
import sys
import os

# this stores the parsed files' hashes, to avoid parsing multiple times
# parsing a single LGP file is a very time-confusing task
# thus, we're saving the hashes of the files to make sure it's only done once
_hashed_files = {}

# after this, we're saving the files' contents themselves in memory
# this is all optimization, and is only used to access the data more than once
_files_contents = {}

# this boolean determines if threading is to be used when parsing the contents
# it can be re-assigned after the module has been imported
USE_THREADING = True

# this is the maximum number of ToC entries that will be parsed per thread,
# if the above is set to True
MAX_LOOKUP_VALUE_PER_THREAD = 200

# the main thread will need to access this lock multiple times
# every other thread needs to access it only once
# however, we need a reentrant lock because of the main thread
ToC_Lock = threading.RLock()

# global mutable objects used for multi-threading
_all_files = {}
_has_conflicts = []
_uniques = []

def _join_hex(hexlist):
    allhexes = reversed([hex(int(str(x))) for x in hexlist])
    return "0x" + "".join(x[2:].zfill(2) for x in allhexes)

def _join_bytes(bytelist):
    new = ""
    for char in bytelist:
        try:
            char = chr(ord(char))
        except TypeError:
            char = chr(char)
        new += char
    return new

def _handle_multi_threading(num, toc):
    has_conflicts = False
    threads_started = 0
    pointer = 16
    while num > 0:
        n = MAX_LOOKUP_VALUE_PER_THREAD
        if num < MAX_LOOKUP_VALUE_PER_THREAD:
            n = num
        _uniques.append(num)
        threading.Thread(None, _parse_toc, args=(n, toc[:n*27], pointer, num)).start()
        toc = toc[n:]
        pointer += n*27
        num -= MAX_LOOKUP_VALUE_PER_THREAD
        threads_started += 1
    while True:
        with ToC_Lock:
            if not _uniques:
                return (_all_files, any(_has_conflicts))
        # it takes roughly 7/200000 of a second per ToC entry
        # rough that up to 10/200000 (or 1/20000) per entry
        # that number, times the maximum amount of entry lookups per thread
        # and that, times the number of threads started, will give us a
        # rough estimate of when all the threads will have completed
        # this will almost never exceed one second
        time.sleep((1/20000 * MAX_LOOKUP_VALUE_PER_THREAD) * threads_started)

def _parse_toc(num, toc, pointer=16, unique=None):
    has_conflicts = False
    files = {}
    while num:
        # iterable through every file
        # fetch the bits about this file, and save the rest
        header, toc = (toc[:27], toc[27:])
        # save the filename for use
        filename, header = (header[:20].decode("utf-8"), header[20:])
        # remove all null bytes terminating the strings
        filename = filename.strip("\x00")
        # 4-bytes integer stating the beginning of the file
        start = _join_hex(header[:4])
        # get the total amount of conflicts for that file
        conflicts = _join_hex(header[5:])
        # keep in memory the conflicts amount for each file
        # also remember the starting position of this index
        files[start] = (filename, pointer, header[4], header[5:])
        # increase our current position in the file
        pointer += 27
        # finally, one last check needs to be done
        # this is completely irrelevant for almost every archive
        # however, magic.lgp (and maybe a few others) have conflicts
        # we keep a boolean around to know if there are any conflicts
        if int(conflicts, 16): # will be non-zero if there are conflicts
            has_conflicts = True
        num -= 1

    if USE_THREADING:
        with ToC_Lock:
            _all_files.update(files)
            _has_conflicts.append(has_conflicts)
            _uniques.remove(unique)
    else:
        return (files, has_conflicts)

def read(file):
    with open(file, "rb") as f:
        _all = f.read()
        # save a hash of the file's contents in memory
        # use sha512 because the files can be really huge
        fhash = hashlib.sha512(_all).hexdigest()
        # if the file was already parsed, the hash is stored in there
        # we return it without parsing the file over again
        # this speeds execution should we need to access the file many times
        if fhash == _hashed_files.get(file):
            return _files_contents[file]
        _hashed_files[file] = fhash
        _files_contents[file] = [[], {}, _all]
        # the first 12 bytes are the file creator; right-aligned
        fcreator, _all = (_all[:12], _all[12:])
        # next up is the amount of files contained in the archive (4 bytes)
        num, _all = (_all[:4], _all[4:])
        # find the actual value of the byte we just got
        # flip the bytes around and calculate that
        num = int(_join_hex(num), 16)
        if USE_THREADING:
            files, has_conflicts = _handle_multi_threading(num, _all[:num*27])
        else:
            files, has_conflicts = _parse_toc(num, _all[:num*27])
        _all = _all[num*27:]
        # past this point, we parsed and saved all files' offsets
        # let's sort the files by order that they appear to find the first
        offsets = sorted(files.keys())
        _files_contents[file][0] = [None] * len(files)
        for i, offset in enumerate(offsets):
            cont = files[offset]
            _files_contents[file][0][i] = (cont[0], cont[1], offset, cont[2])
        # after this, we have re-ordered all the files in appearance order
        # now, we need to find the beginning header of each file
        # the key to this dict will be the file's ToC offset
        # the value will be the subdirectory it's in
        # it's defined here so it's always available
        if has_conflicts:
            # if there are conflicts, then the fun begins
            # we need to get the conflicts table out for this
            # thanks to Aali we have a pretty good idea of how it works
            ffile = int(_files_contents[file][0][0][2], 16)
            conflicts_table = _all[:ffile]
            while conflicts_table:
                # the name of the subdirectory is 128 bytes long
                num = int(_join_hex(conflicts_table[:2]), 16)
                while num:
                    all_conflicts[int(_join_hex(conflicts_table[130:132]), 16)] = (
                        _join_bytes(conflicts_table[2:130]).strip("\x00"))
                    print(_join_bytes(conflicts_table[2:130]), num, len(conflicts_table))
                    conflicts_table = conflicts_table[132:]
                    num -= 1

        # whether it has conflicts or not, it's time to extract them
        for filename, cursor, offset, conflicts in ordfiles:
            # this will dynamically check for any conflict
            directory = all_conflicts.get(cursor, "")
            new = total[int(offset, 16):]
            fname, new = (new[:20], new[20:])
            flen, new = (new[:4], new[4:])
            flen = int(_join_hex(flen), 16)
            data = new[:flen]
            with open(os.path.join(folder, directory, filename), "wb") as w:
                w.write(data)


