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
# the last 2 bytes of each ToC entry state the amount of conflicts
# for each of those there are 2 other bytes that tell you
# how many subdirectories there are for each conflict;
# and THEN, we need to read a 128-byte string (the name of the subdirectory)
# then there are two bytes that tell us the ToC index it corresponds to

# HUGE thanks to Andy_S of EsperNet, who helped me through this headache
# I have never really messed around with file formats before, so I knew nothing
# he helped me find my way through this and make it work as it should

import os

def _join_hex(hexlist):
    return "0x" + "".join(x[2:].zfill(2) for x in hexlist)

def extract(file, folder=None):
    if folder is None:
        indx = 0
        if "." in file:
            indx = file.index(".")
        folder = os.path.join(os.getcwd(), file[indx:])
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
        # the character's lexicography is checked and we get the # of files
        num = ord(num.decode("utf-8").strip("\x00"))
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
            allbytes = reversed([hex(int(str(x))) for x in file[:4]])
            start = _join_hex(allbytes)
            # keep in memory the conflicts amount for each file
            # also remember the starting position of this index
            files[start] = (filename, pointer, file[4], file[6])
            # increase our position for each parsed file
            pointer += 27
            # finally, one last check needs to be done
            # this is completely irrelevant for almost every archive
            # however, magic.lgp (and maybe a few others) have conflicts
            # we keep a boolean around to know if there are any conflicts
            if file[6]: # will be non-zero if there are conflicts
                has_conflicts = True
            num -= 1
        # past this point, we parsed and saved all files' offsets
        # let's sort the files by order that they appear to find the first
        offsets = sorted(files.keys())
        ordfiles = [None] * len(files)
        for i, offset in enumerate(offsets):
            file = files[offset]
            ordfiles[i] = (file[0], pointer, offset, file[3])
        # after this, we have re-ordered all the files in appearance order
        # now, we need to find the beginning header of each file
        if not has_conflicts:
            # assuming we have not found any conflicts, our job here is done
            # we just extract the files to disk, not caring about conflicts
            for filename, pointer, offset, conflicts in ordfiles:
                new = total[int(offset, 16):]
                fname, new = (new[:20], new[20:])
                flen, new = (new[:4], new[4:])
                flen = reversed([hex(int(str(x))) for x in flen])
                flen = int(_join_hex(flen), 16)
                data = new[:flen]
                with open(os.path.join(self.folder, filename), "wb") as w:
                    w.write(data)


