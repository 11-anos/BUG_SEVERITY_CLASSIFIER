#include <cstdlib>

void good() {
    int* p = (int*)malloc(sizeof(int));
    *p = 1;
    free(p);
}

void bad_missing_free() {
    int* p = (int*)malloc(sizeof(int));
    *p = 1;
}

void bad_conditional_free(int flag) {
    int* p = (int*)malloc(sizeof(int));
    if (flag) {
        free(p);
    }
}