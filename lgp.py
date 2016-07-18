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

__version__ = "0.1"
__author__ = "Vgr"

_libname_ = __file__[-list(reversed(__file__.replace("\\", "/"))).index("/"):]

import hashlib
import sys
import os

# this stores the parsed files' hashes, to avoid parsing multiple times
# parsing a single LGP file is a very time-confusing task
# thus, we're saving the hashes of the files to make sure it's only done once
_hashed_files = {}

# after this, we're saving the files' contents themselves in memory
# this is all optimization, and is only used to access the data more than once
_files_contents = {}

def _parse_toc(num, toc, pointer=16):
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
        start = hex(int.from_bytes(header[:4], "little"))
        # get the total amount of conflicts for that file
        conflicts = hex(int.from_bytes(header[5:], "little"))
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

    return (files, has_conflicts)

def read(file):
    with open(file, "rb") as f:
        _all = f.read()
        # strip the path from the file, to get only the filename
        if "/" in file or "\\" in file:
            file = file[-list(reversed(file.replace("\\", "/"))).index("/"):]
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
        # then the number of files in the archive (4 bytes integer)
        fcreator, num, _all = (_all[:12], _all[12:16], _all[16:])
        # find the actual value of the byte we just got
        # flip the bytes around and calculate that
        num = int.from_bytes(num, "little")
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
            # before the conflicts table, there's the lookup table
            # I don't know what it does, but it's 3602 bytes long
            # let's just skip them until I learn their purpose
            # the last 2 bytes are the amount of conflicts though, so keep it
            # the lookup table in an LGP file is used to quickly find files by name
            # (PC version wasn't fast enough to scan the entire ToC back in '98)
            # you calculate a lookup value from the first two characters of the
            # file name and that becomes the index into the table
            # of course its not necessary to extract an archive, its only used for random file access
            # so you need to be able to create a lookup table for your LGP when packing but you can just ignore it when unpacking
            _all = _all[3600:]
            # this is how to read the conflicts table, according to dessertmode
            # read "conflict table size" (2-byte integer)
            # repeat "conflict table size" times:
            #   read "number of conflicts" (2-byte integer)
            #   repeat "number of conflicts" times:
            #     read "name" (128-byte string)
            #     read "TOC index" (2-byte integer)
            conflicts_amount, _all = (int.from_bytes(_all[:2], "little"), _all[2:])
            while conflicts_amount:
                conflicts_num, _all = (int.from_bytes(_all[:2], "little"), _all[2:])
                while conflicts_num:
                    subdir, _all = (_all[:128].decode("utf-8"), _all[128:])
                    toc, _all = (int.from_bytes(_all[:2], "little"), _all[2:])
                    _files_contents[file][1][toc] = subdir.replace("\x00", "")
                    conflicts_num -= 1
                conflicts_amount -= 1

        return _files_contents[file]

def extract(file, folder=None):
    if folder is None:
        indx = None
        if "." in file:
            indx = file.index(".")
        folder = os.path.join(os.getcwd(), file[:indx])
    if not os.path.isdir(folder):
        os.mkdir(folder)
    folder = folder.replace("\\", "/")

    files, all_conflicts, total = read(file)

    for filename, cursor, offset, conflicts in files:
        # this will dynamically check for any conflict
        directory = all_conflicts.get(cursor, "")
        directory = directory.replace("\\", "/").replace("\x00", "")
        if directory and not os.path.isdir(os.path.join(folder, directory)):
            new = folder
            for fold in directory.split("/"):
                new = os.path.join(new, fold)
                if not os.path.isdir(new):
                    os.mkdir(new)
        new = total[int(offset, 16):]
        fname, new = (new[:20], new[20:])
        flen, new = (new[:4], new[4:])
        flen = int.from_bytes(flen, "little")
        data = new[:flen]
        with open(os.path.join(folder, directory, filename), "wb") as w:
            w.write(data)

def print_help():
    print("Python 3 library for Final Fantasy VII's LGP files.", "",
          "  Author: " + __author__, "  Version: " + __version__, "",
          "Available command line parameters:",
          "--extract    Extract an archive into a folder",
          "Usage: %s --extract <file> [directory]" % _libname_, "",
          # not implemented yet
          # "--repack     Repack a folder into an archive",
          # "Usage: %s --repack <directory> [file]" % _libname_, "",
          # "--insert     Insert a folder into an archive"
          # "Usage: %s --insert <directory> [file]" % _libname_, "",
          "--help       Display this help message",
          "Usage: %s --help" % _libname_, sep="\n")

if len(sys.argv) == 2:
    if os.path.isfile(sys.argv[1]):
        extract(sys.argv[1])
    # elif os.path.isdir(sys.argv[1]):
    #     repack(sys.argv[1])

if len(sys.argv) == 3:
    param, file = sys.argv[1:]
    if param in ("-e", "--extract"):
        if os.path.isfile(file):
            extract(file)
        else:
            print("Error: '%s' is not a file." % file)

    # if param in ("-r", "--repack"):
    #     if os.path.isdir(file):
    #         repack(file)
    #     else:
    #         print("Error: '%s' is not a directory." % file)

    # if param in ("-i", "--insert"):
    #    if os.path.isdir(file):
    #         insert(file)
    #     else:
    #         print("Error: '%s' is not a directory." % file)

    if param in ("-h", "--help"):
        print_help()

if len(sys.argv) == 4:
    param, file, folder = sys.argv[1:]
    if param in ("-e", "--extract"):
        if os.path.isfile(file):
            extract(file, folder)
        else:
            print("Error: '%s' is not a file." % file)

    # if param in ("-r", "--repack"):
    #     if os.path.isdir(file):
    #         repack(file, folder) # it's actually the other way around
    #     else:
    #         print("Error: '%s' is not a directory." % file)

    # if param in ("-i", "--insert"):
    #     if os.path.isdir(file):
    #         insert(file, folder):
    #     else:
    #         print("Error: '%s' is not a directory." % file)


if __name__ == "__main__":
    print_help()



































