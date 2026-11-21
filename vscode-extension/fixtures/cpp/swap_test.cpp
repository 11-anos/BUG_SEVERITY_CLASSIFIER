void f(int* a) {
    swap(a[0], a[1]);
    if (a != nullptr) {
        swap(a[1], a[2]);
    }
    if (a[0] > 0)
        swap(a[2], a[3]);
}