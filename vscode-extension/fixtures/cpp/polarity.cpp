void f(int* p, int* q) {
    if (!p) return;
    *p = 1;

    if (p == nullptr) {
        *p = 2;
    }

    if (p != nullptr) {
        *p = 3;
    }

    if (p != nullptr) return;
    *p = 4;

    if (!q) return;
    *q = 5;
}