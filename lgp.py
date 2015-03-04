# the first 12 bytes are the file creator
# then a 4-bytes integer about the number of files

# Table of Contents; each entry is like this:
# sequence of null-terminated 20-bytes-long string; filename
# 4-bytes giving the starting offset of each file
# 1 byte of apparently unused data
# 2 bytes saying the number of conflicts

# after that, the conflicts table, according to Aali
# the wiki (ficedula) states it's typically 3602 bytes long
# however I can never get that short; oh well, for now it's not too bad
# compare the end of the ToC against the beginning of the first file

# Conflicts explained, courtesy of Aali:
# the last 2 bytes (mentioned above) of each ToC entry state the amount of conflicts
# for each of those there are 2 other bytes that tells you how many subdirectories there are for each conflict
# and THEN, we need to read a 128-byte string (the name of the subdirectory) and two bytes that tell us the ToC index it corresponds to

import os

class LGPHandler:
    def __init__(self, file, folder):
        self.file = file
        self.folder = folder
        if not os.path.isdir(folder):
            os.mkdir(folder)

    def extract(self):
        with open(self.file, "rb") as f:
            _all = f.read()
            total = _all # save for future reference
            pointer = 0 # our current position in the file
            # the first 12 bytes are the file creator; right-aligned
            fcreator, _all = (_all[:12], _all[12:])
            pointer += 11
            # next up is the amount of files contained in the archive (4 bytes)
            num, _all = (_all[:4], _all[4:])
            pointer += 3
            # find the actual value of the byte we just got
            # the character's lexicography is checked and we get the # of files
            num = ord(num.decode("utf-8")[0])
            files = {}
            while num:
                # iterable through every file
                # fetch the bits about this file, and save the rest
                file, _all = (_all[:27], _all[27:])
                # increase our position for each parsed file
                pointer += 26
                # save the filename for use
                filename, file = (file[:20].decode("utf-8"), file[20:])
                # remove all null bytes terminating the strings
                filename = filename.strip("\x00")
                # this is a hacky way around it, but there's no better way
                # decoding fails in certain cases, while str() does not
                start = int("".join(str(x) for x in file[:4]))
                files[start] = (filename, pointer-26, file[4], file[4:6])
                # keep in memory the conflicts amount for each file
                # also remember the starting position of this index
                num -= 1
            # past this point, we parsed and saved all files' offsets
            # let's sort the files by order that they appear to find the first
            offsets = sorted(files.keys())
            ordfiles = [None] * len(files)
            for i, offset in enumerate(offsets):
                file = files[offset]
                ordfiles[i] = (file[0], offset) + file[2:]
            # after this, we have re-ordered all the files in appearance order
            # calculate where we are with the total length and files
            ffile = ordfiles[0][1] # get the offset of the first file
