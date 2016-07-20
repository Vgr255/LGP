#include "Python.h"
#include "_lgpmodule.h"

/* To do:
 *
 * 1 - Write a simple function that doesn't do much
 * 2 - Convert some parts of the unlgp.c bits into proper Python stuff
 * 3 - Make a few functions that can read a file and return the contents
 * 4 - Properly fetch everything from a file
 * 5 - Convert the parts of lgp.c into proper Python stuff
 * 6 - Make some functions that can properly encode stuff into LGPs
 * 7 - Make a full Python class in C for all LGP stuff in and out
 */

/* shared part */

void *malloc_read(FILE *f, int size)
{
    char *ret = malloc(size);
    char *data = ret;
    int res;

    do
    {
        res = fread(data, 1, size, f);
        if(res != 0)
        {
            size -= res;
            data += res;
        }
        else return ret;
    } while(size);

    return ret;
}

/* lgp.c part */

struct file_list
{
    struct file_header file_header;
    char source_name[256];
    int toc_index;
    int conflict;
    struct file_list *next;
};

struct conflict_entry conflicts[MAX_CONFLICTS][255];
unsigned short num_conflict_entries[MAX_CONFLICTS];

struct lookup_table_entry lookup_table[LOOKUP_TABLE_ENTRIES];
struct file_list *lookup_list[LOOKUP_TABLE_ENTRIES];

int files_read = 0;
int files_total = 0;

int read_directory(char *base_path, char *path, DIR *d)
{
    struct dirent *dent;
    char tmp[1024];

    while((dent = readdir(d)))
    {
        int lookup_value1;
        int lookup_value2;
        int lookup_index;
        struct file_list *file;
        struct file_list *last;
        struct stat s;

        if(!strcmp(dent->d_name, ".") || !strcmp(dent->d_name, "..")) continue;

        files_total++;

        if(strlen(dent->d_name) > 15)
        {
            PyErr_Format(PyExc_ValueError, "Filename too long: %s", dent->d_name);
            return -1;
        }

        sprintf(tmp, "%s/%s/%s", base_path, path, dent->d_name);

        if(stat(tmp, &s))
        {
            PyErr_Format(PyExc_OSError, "Could not stat input file: %s", dent->d_name);
            return -1;
        }

        if(!S_ISREG(s.st_mode))
        {
            DIR *new_d;
            char new_path[1024];

            files_total--;

            new_d = opendir(tmp);

            if(!new_d)
            {
                PyErr_Format(PyExc_OSError, "Error opening input directory %s", tmp);
                return -1;
            }

            if(strcmp(path, "")) sprintf(new_path, "%s/%s", path, dent->d_name);
            else strcpy(new_path, dent->d_name);

            read_directory(base_path, new_path, new_d);

            closedir(new_d);

            continue;
        }

        lookup_value1 = lgp_lookup_value(dent->d_name[0]);
        lookup_value2 = lgp_lookup_value(dent->d_name[1]);

        if(lookup_value1 > LOOKUP_VALUE_MAX || lookup_value1 < 0 || lookup_value2 > LOOKUP_VALUE_MAX || lookup_value2 < -1)
        {
            PyErr_Format(PyExc_ValueError, "Invalid filename: %s", dent->d_name);
            return -1;
        }

        lookup_index = lookup_value1 * LOOKUP_VALUE_MAX + lookup_value2 + 1;

        lookup_table[lookup_index].num_files++;

        last = lookup_list[lookup_index];

        if(last) while(last->next) last = last->next;

        file = calloc(sizeof(*file), 1);
        strcpy(file->file_header.name, dent->d_name);
        sprintf(file->source_name, "%s/%s", path, dent->d_name);
        file->file_header.size = s.st_size;
        file->next = 0;

        if(last) last->next = file;
        else lookup_list[lookup_index] = file;

        files_read++;
    }
    return 0;
}

static PyObject *
lgp_pack(PyObject *self, PyObject *args)
{
    DIR *d;
    FILE *f;
    int toc_size;
    int toc_index = 0;
    int offset = 0;
    int i;
    char tmp[512];
    int conflict_table_size = 2;
    unsigned short num_conflicts = 0;
    char *directory;
    char *archive;

    if (!PyArg_ParseTuple(args, "ss:pack", &directory, &archive))
        return NULL;

    d = opendir(directory);

    if (!d) {
        PyErr_SetString(PyExc_OSError, "Error opening input directory");
        return NULL;
    }

    memset(lookup_table, 0, sizeof(lookup_table));

    if (read_directory(directory, "", d) < 0)
    {
        closedir(d);
        return NULL;
    }

    closedir(d);

    if (!files_read)
    {
        PyErr_SetString(PyExc_ValueError, "No input files found.");
        return NULL;
    }

    if (!unlink(archive))
    {
        PyErr_Format(PyExc_OSError, "Could not unlink %s", archive);
        return NULL;
    }
    f = fopen(archive, "wb");

    if(!f)
    {
        PyErr_Format(PyExc_OSError, "Error opening output file %s", archive);
        return NULL;
    }

    /* printf("Number of files to add: %i\n", files_read); */

    if (fwrite("\0\0SQUARESOFT", 12, 1, f) < 0)
    {
        PyErr_SetString(PyExc_OSError, "Could not write to file");
        return NULL;
    }
    if (fwrite(&files_read, 4, 1, f) < 0)
    {
        PyErr_SetString(PyExc_OSError, "Could not write to file");
        return NULL;
    }

    for(i = 0; i < LOOKUP_TABLE_ENTRIES; i++)
    {
        struct file_list *file = lookup_list[i];

        while(file)
        {
            file->toc_index = toc_index++;
            file = file->next;
        }
    }

    for(i = 0; i < LOOKUP_TABLE_ENTRIES; i++)
    {
        struct file_list *file = lookup_list[i];

        while(file)
        {
            if(!file->conflict)
            {
                struct file_list *file2 = lookup_list[i];

                /* debug_printf("Finding conflict for file %s\n", file->file_header.name); */

                while(file2)
                {
                    if(!strcmp(file->file_header.name, file2->file_header.name) && file != file2)
                    {
                        if(num_conflict_entries[num_conflicts] == 0)
                        {
                            /* debug_printf("New conflict %i (%s)\n", num_conflicts + 1, file->file_header.name); */

                            file->conflict = num_conflicts + 1;
                            strncpy(conflicts[num_conflicts][0].name, file->source_name, strlen(file->source_name) - strlen(file->file_header.name) - 1);
                            conflicts[num_conflicts][0].toc_index = file->toc_index;
                            num_conflict_entries[num_conflicts]++;

                            conflict_table_size += 130;
                        }

                        file2->conflict = num_conflicts + 1;
                        strncpy(conflicts[num_conflicts][num_conflict_entries[num_conflicts]].name, file2->source_name, strlen(file2->source_name) - strlen(file2->file_header.name) - 1);
                        conflicts[num_conflicts][num_conflict_entries[num_conflicts]].toc_index = file2->toc_index;
                        num_conflict_entries[num_conflicts]++;

                        conflict_table_size += 130;
                    }

                    file2 = file2->next;
                }

                if(num_conflict_entries[num_conflicts] != 0)
                {
                    num_conflicts++;
                    conflict_table_size += 2;
                }
            }
            /* else debug_printf("Not finding conflict for file %s (%i)\n", file->file_header.name, file->conflict); */

            file = file->next;
        }
    }

    /* if(num_conflicts) debug_printf("%i conflicts\n", num_conflicts); */

    toc_size = files_read * sizeof(struct toc_entry);

    for(i = 0; i < LOOKUP_TABLE_ENTRIES; i++)
    {
        struct file_list *file = lookup_list[i];
        struct toc_entry toc;

        if(file) lookup_table[i].toc_offset = file->toc_index + 1;

        while(file)
        {
            memcpy(toc.name, file->file_header.name, 20);
            toc.offset = 16 + files_read * sizeof(struct toc_entry) + LOOKUP_TABLE_ENTRIES * 4 + conflict_table_size + offset;
            toc.unknown = 14;
            toc.conflict = file->conflict;

            if (fwrite(&toc, sizeof(struct toc_entry), 1, f) < 0)
            {
                PyErr_SetString(PyExc_OSError, "Could not write to file");
                return NULL;
            }

            offset += sizeof(file->file_header) + file->file_header.size;

            file = file->next;
        }
    }

    if (fwrite(lookup_table, sizeof(lookup_table), 1, f) < 0)
    {
        PyErr_SetString(PyExc_OSError, "Could not write to file");
        return NULL;
    }

    if (fwrite(&num_conflicts, 2, 1, f) < 0)
    {
        PyErr_SetString(PyExc_OSError, "Could not write to file");
        return NULL;
    }

    for(i = 0; i < MAX_CONFLICTS; i++)
    {
        if(num_conflict_entries[i] > 0)
        {
            if (fwrite(&num_conflict_entries[i], 2, 1, f) < 0)
            {
                PyErr_SetString(PyExc_OSError, "Could not write to file");
                return NULL;
            }
            if (fwrite(conflicts[i], sizeof(**conflicts), num_conflict_entries[i], f) < 0)
            {
                PyErr_SetString(PyExc_OSError, "Could not write to file");
                return NULL;
            }
        }
    }

    for(i = 0; i < LOOKUP_TABLE_ENTRIES; i++)
    {
        struct file_list *file = lookup_list[i];

        while(file)
        {
            FILE *inf;
            char *data;

            sprintf(tmp, "%s/%s", directory, file->source_name);
            inf = fopen(tmp, "rb");

            if (!inf)
            {
                PyErr_Format(PyExc_OSError, "Error opening input file: %s", file->source_name);
                unlink(archive);
                return NULL;
            }

            data = malloc_read(inf, file->file_header.size);

            if (fwrite(&file->file_header, sizeof(file->file_header), 1, f) < 0)
            {
                PyErr_SetString(PyExc_OSError, "Could not write to file");
                return NULL;
            }

            if (fwrite(data, file->file_header.size, 1, f) < 0)
            {
                PyErr_SetString(PyExc_OSError, "Could not write to file");
                return NULL;
            }

            if (fclose(inf) < 0)
            {
                PyErr_SetString(PyExc_OSError, "Could not close file");
                return NULL;
            }

            free(data);

            file = file->next;
        }
    }

    if (fwrite("FINAL FANTASY7", 14, 1, f) < 0)
    {
        PyErr_SetString(PyExc_OSError, "Could not write to file");
        return NULL;
    }

    if (fclose(f) < 0)
    {
        PyErr_SetString(PyExc_OSError, "Could not close file");
        return NULL;
    }

    /* printf("Successfully created archive with %i file(s) out of %i file(s) total.\n", files_read, files_total); */

    Py_RETURN_NONE;
}

PyDoc_STRVAR(pack_doc, "LGP Repacker function");

/* unlgp.c part */

static PyObject *
lgp__unpack(PyObject *self, PyObject *args)
{
    FILE *f;
    char tmp[512];
    int num_files;
    int i;
    int k;
    int files_written = 0;
    unsigned short num_conflicts;
    struct toc_entry *toc;
    struct lookup_table_entry *lookup_table;
    struct conflict_entry *conflicts[MAX_CONFLICTS];
    int num_conflict_entries[MAX_CONFLICTS];
    const char *archive;
    /* Verbosity level for various purposes 
     * 0 = Only warnings are displayed
     * 1 = Some information is displayed as well
     * 2 = All debug information is shown
     * -1 = Nothing is ever displayed, not even warnings
     */
    int verbosity = 0;

    if (!PyArg_ParseTuple(args, "si:unpack", &archive, &verbosity))
        return NULL;

    f = fopen(archive, "rb");

    if (!f)
    {
        PyErr_SetString(PyExc_OSError, "Error opening input file");
        return NULL;
    }

    if (!fread(tmp, 12, 1, f) || !fread(&num_files, 4, 1, f))
    {
        PyErr_SetString(PyExc_EOFError, "Unexpected EOF reached in archive header");
        goto fail_1;
    }

    if (verbosity > 0)
        PySys_WriteStdout("Number of files in archive: %i\n", num_files);

    toc = malloc(sizeof(*toc) * num_files);
    for(i = 0; i < num_files; i++)
    {
        if (!fread(&toc[i].name, 20, 1, f) ||
            !fread(&toc[i].offset, 4, 1, f) ||
            !fread(&toc[i].unknown, 1, 1, f) ||
            !fread(&toc[i].conflict, 2, 1, f))
        {
            PyErr_SetString(PyExc_EOFError, "Unexpected EOF reached in ToC");
            goto fail_2;
        }
    }

    lookup_table = malloc(sizeof(*lookup_table) * LOOKUP_TABLE_ENTRIES);
    for(i = 0; i < LOOKUP_TABLE_ENTRIES; i++)
    {
        if (!fread(&lookup_table[i].toc_offset, 2, 1, f) ||
            !fread(&lookup_table[i].num_files, 2, 1, f))
        {
            PyErr_SetString(PyExc_EOFError, "Unexpected EOF reached in lookup table");
            goto fail_3;
        }
    }

    if (!fread(&num_conflicts, 2, 1, f))
    {
        PyErr_SetString(PyExc_EOFError, "Unexpected EOF reached while reading conflicts");
        goto fail_3;
    }

    if (verbosity > 0)
        PySys_WriteStdout("%i conflicts\n", num_conflicts);

    for(k = 0; k < num_conflicts; k++)
    {
        if (!fread(&num_conflict_entries[k], 2, 1, f))
        {
            PyErr_SetString(PyExc_EOFError, "Unexpected EOF reached in conflicts table");
            goto fail_3;
        }

        if (verbosity > 1)
            PySys_WriteStdout("%i: %i conflict entries\n", i, num_conflict_entries[k]);

        conflicts[k] = malloc(sizeof(**conflicts) * num_conflict_entries[k]);

        if (!fread(&conflicts[k]->name, 128, 1, f) ||
            !fread(&conflicts[k]->toc_index, 2, 1, f))
        {
            PyErr_SetString(PyExc_EOFError, "Unexpected EOF reached in conflicts parsing");
            goto fail_4;
        }
    }

    if (verbosity > 0)
        PySys_WriteStdout("Done dealing with conflicts\n");

    for(i = 0; i < num_files; i++)
    {
        struct file_header *file_header;
        void *data;
        FILE *of;
        int lookup_value1;
        int lookup_value2;
        struct lookup_table_entry *lookup_result;
        int resolved_conflict = 0;
        char name[256];

        if (verbosity > 1)
            PySys_WriteStdout("%i; Name: %s, offset: 0x%x, unknown: 0x%x, conflict: %i\n", i, toc[i].name, toc[i].offset, toc[i].unknown, toc[i].conflict);

        if (fseek(f, toc[i].offset, SEEK_SET))
        {
            PyErr_SetString(PyExc_EOFError, "Unexpected EOF in file header seeking");
            goto fail_4;
        }

        file_header = malloc(sizeof(*file_header));

        if (!fread(&file_header->name, 20, 1, f) ||
            !fread(&file_header->size, 4, 1, f))
        {
            PyErr_SetString(PyExc_EOFError, "Unexpected EOF in file header parsing");
            free(file_header);
            goto fail_4;
        }

        if (verbosity > 1)
            PySys_WriteStdout("%i; Name: %s, size: %i\n", i, file_header->name, file_header->size);
        if (verbosity > 2)
            PySys_WriteStdout("%s %s\n", toc[i].name, file_header->name);

        if(!strcmp(toc[i].name, file_header->name/*, 20*/))
        {
            PyErr_Format(PyExc_ValueError, "Offset error: %s", toc[i].name);
            free(file_header);
            goto fail_4;
        }

        lookup_value1 = lgp_lookup_value(toc[i].name[0]);
        lookup_value2 = lgp_lookup_value(toc[i].name[1]);

        lookup_result = &lookup_table[lookup_value1 * LOOKUP_VALUE_MAX + lookup_value2 + 1];

        if (verbosity > 2)
            PySys_WriteStdout("%i; %i - %i\n", i, (lookup_result->toc_offset - 1), (lookup_result->toc_offset - 1 + lookup_result->num_files));
        if (verbosity > 1)
            PySys_WriteStdout("i: %i\ntoc offset: %i\nnum files: %i\n", i, lookup_result->toc_offset, lookup_result->num_files);

        if ((i < (lookup_result->toc_offset - 1) || i > (lookup_result->toc_offset - 1 + lookup_result->num_files)) && verbosity > -1)
            PySys_WriteStdout("Warning: Broken lookup table, FF7 may not be able to find %s\n", toc[i].name);

        strcpy(name, archive);
        strcat(name, "_output");
        mkdir(name, 0777);
        strcat(name, "/");
        strcat(name, toc[i].name);

        if(toc[i].conflict != 0)
        {
            int j;
            int conflict = toc[i].conflict - 1;

            if (verbosity > 1)
                PySys_WriteStdout("Trying to resolve conflict %i for %i (%s)\n", conflict, i, toc[i].name);

            for(j = 0; j < num_conflict_entries[conflict]; j++)
            {
                if(conflicts[conflict][j].toc_index == i)
                {
                    sprintf(name, "%s/%s", conflicts[conflict][j].name, toc[i].name);
                    if (verbosity > 1)
                        PySys_WriteStdout("Conflict resolved to %s\n", name);
                    resolved_conflict = 1;
                    break;
                }
            }

            if(!resolved_conflict)
            {
                PyErr_Format(PyExc_ValueError, "Unresolved conflict for %s", toc[i].name);
                free(file_header);
                goto fail_4;
            }
        }

        if (verbosity > 1)
            PySys_WriteStdout("Extracting %s\n", name);

        if(resolved_conflict)
        {
            char *next = name;

            while((next = strchr(next, '/')))
            {
                char tmp[256];

                while(next[0] == '/') next++;

                strncpy(tmp, name, next - name);
                tmp[next - name] = 0;

                if (verbosity > 1)
                    PySys_WriteStdout("Creating directory %s\n", tmp);

                if (!mkdir(tmp, 0777))
                {
                    PyErr_Format(PyExc_OSError, "Could not create directory %s", tmp);
                    free(file_header);
                    goto fail_4;
                }
            }
        }

        data = malloc(file_header->size);

        if (!fread(data, file_header->size, 1, f))
        {
            PyErr_SetString(PyExc_ValueError, "Could not read data");
            free(file_header);
            free(data);
            goto fail_4;
        }

        of = fopen(name, "wb");
        PySys_WriteStdout("After opening file, trying to write\n");

        if(!of)
        {
            PyErr_Format(PyExc_OSError, "Error opening output file %s", name);
            free(file_header);
            free(data);
            goto fail_4;
        }

        if (!fwrite(data, file_header->size, 1, of))
        {
            PyErr_Format(PyExc_OSError, "Could not write %s to %s", name, tmp);
            free(file_header);
            free(data);
            goto fail_4;
        }
        PySys_WriteStdout("After writing\n");

        fclose(of);
        free(file_header);
        free(data);

        files_written++;
    }

    if (verbosity > 0)
        PySys_WriteStdout("Successfully extracted %i file(s) out of %i file(s) total\n", files_written, num_files);

    fclose(f);
    free(toc);
    free(lookup_table);

    for (i = 0; i < (k+1) && i < num_conflicts; i++)
        free(conflicts[i]);

    Py_RETURN_NONE;

fail_4:
    for (i = 0; i < num_conflicts; i++)
        free(conflicts[i]);
fail_3:
    free(lookup_table);
fail_2:
    free(toc);
fail_1:
    fclose(f);
    return NULL;

}

PyDoc_STRVAR(unpack_doc, "Function for unpacking LGP files.");

static struct PyMethodDef lgp_methods[] = {
    {"pack",        lgp_pack,    METH_VARARGS,   pack_doc},
    {"_unpack", (PyCFunction)lgp__unpack, METH_VARARGS, unpack_doc},
    {NULL,          NULL},
};

PyDoc_STRVAR(lgp_doc, "Test lgp module.");

static struct PyModuleDef lgpmodule = {
    PyModuleDef_HEAD_INIT,
    "_lgp",
    lgp_doc,
    0, /* multiple "initialization" just copies the module dict. */
    lgp_methods,
    NULL,
    NULL,
    NULL,
    NULL
};

PyMODINIT_FUNC
PyInit__lgp(void)
{
    return PyModule_Create(&lgpmodule);
}
