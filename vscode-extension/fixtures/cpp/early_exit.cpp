#include <bits/stdc++.h>
using namespace std;

void process(int* p, int* q) {
    if (!p) return;

    int a = *p;
    cout << a << endl;

    if (!q) {
        cout << "no q" << endl;
        return;
    }

    int b = *q;
    int c = *p;

    if (a > 0) {
        cout << "positive" << endl;
    }
    cout << b << endl;
}