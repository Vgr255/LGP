# the first 12 bytes are the file creator
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

import os

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

def extract(file, folder=None):
    if folder is None:
        indx = None
        if "." in file:
            indx = file.index(".")
        folder = os.path.join(os.getcwd(), file[:indx])
    if not os.path.isdir(folder):
        os.mkdir(folder)
    with open(file, "rb") as f:
        _all = f.read()
        has_conflicts = False
        total = _all # save for future reference
        pointer = 0 # our current position in the file
        # the first 12 bytes are the file creator; right-aligned
        fcreator, _all = (_all[:12], _all[12:])
        pointer += 12
        # next up is the amount of files contained in the archive (4 bytes)
        num, _all = (_all[:4], _all[4:])
        pointer += 4
        # find the actual value of the byte we just got
        # flip the bytes around and calculate that
        num = int(_join_hex(num), 16)
        files = {}
        while num:
            # iterable through every file
            # fetch the bits about this file, and save the rest
            file, _all = (_all[:27], _all[27:])
            # save the filename for use
            filename, file = (file[:20].decode("utf-8"), file[20:])
            # remove all null bytes terminating the strings
            filename = filename.strip("\x00")
            # 4-bytes integer stating the beginning of the file
            # these are backwards, so reverse it
            start = _join_hex(file[:4])
            # get the total amount of conflicts for that file
            conflicts = _join_hex(file[5:])
            # keep in memory the conflicts amount for each file
            # also remember the starting position of this index
            files[start] = (filename, pointer, file[4], file[5:])
            # increase our position for each parsed file
            pointer += 27
            # finally, one last check needs to be done
            # this is completely irrelevant for almost every archive
            # however, magic.lgp (and maybe a few others) have conflicts
            # we keep a boolean around to know if there are any conflicts
            if int(conflicts, 16): # will be non-zero if there are conflicts
                has_conflicts = True
            num -= 1
        # past this point, we parsed and saved all files' offsets
        # let's sort the files by order that they appear to find the first
        offsets = sorted(files.keys())
        ordfiles = [None] * len(files)
        for i, offset in enumerate(offsets):
            file = files[offset]
            ordfiles[i] = (file[0], file[1], offset, file[3])
        # after this, we have re-ordered all the files in appearance order
        # now, we need to find the beginning header of each file
        # the key to this dict will be the file's ToC offset
        # the value will be the subdirectory it's in
        # it's defined here so it's always available
        all_conflicts = {}
        if has_conflicts:
            # if there are conflicts, then the fun begins
            # we need to get the conflicts table out for this
            # thanks to Aali we have a pretty good idea of how it works
            ffile = int(ordfiles[0][2], 16)
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


