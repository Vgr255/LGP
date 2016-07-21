#ifndef _LGPMODULE_H
#define _LGPMODULE_H

#ifdef __cplusplus
extern "C" {
#endif

#include <ctype.h>
#include <stdio.h>
#include <string.h>
#include <malloc.h>
#include <sys/stat.h>

#define LOOKUP_VALUE_MAX 30
#define LOOKUP_TABLE_ENTRIES LOOKUP_VALUE_MAX * LOOKUP_VALUE_MAX

#define MAX_CONFLICTS 4096

#ifdef _WIN32
#include "_dirent.h"
#include <direct.h>
#define mkdir(path, mode) _mkdir(path)
#else
#include <dirent.h>
#endif

typedef struct _lgp {
    PyObject_HEAD
    const char *file;
} _LGPObject;

struct toc_entry
{
    char name[20];
    unsigned int offset;
    unsigned char unknown;
    unsigned short conflict;
};

struct file_header
{
    char name[20];
    unsigned int size;
};

struct lookup_table_entry
{
    unsigned short toc_offset;
    unsigned short num_files;
};

struct conflict_entry
{
    char name[128];
    unsigned short toc_index;
};

inline int lgp_lookup_value(unsigned char c)
{
    c = tolower(c);

    if(c == '.') return -1;

    if(c < 'a' && c >= '0' && c <= '9') c += 'a' - '0';

    if(c == '_') c = 'k';
    if(c == '-') c = 'l';

    return c - 'a';
}


#ifdef __cplusplus
}
#endif
#endif /* !_LGPMODULE_H */
