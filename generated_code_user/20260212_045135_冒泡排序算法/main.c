#include <stdio.h>
#include <stdlib.h>

static void bubble_sort(int *a, int n) {
    for (int i = 0; i < n - 1; i++) {
        int swapped = 0;
        for (int j = 0; j < n - 1 - i; j++) {
            if (a[j] > a[j + 1]) {
                int tmp = a[j];
                a[j] = a[j + 1];
                a[j + 1] = tmp;
                swapped = 1;
            }
        }
        if (!swapped) {
            break;
        }
    }
}

int main(void) {
    int n;
    if (scanf("%d", &n) != 1) {
        fprintf(stderr, "输入格式：先输入 n，再输入 n 个整数\n");
        return 1;
    }
    if (n <= 0) {
        putchar('\n');
        return 0;
    }

    int *a = (int *)malloc((size_t)n * sizeof(int));
    if (!a) {
        fprintf(stderr, "内存分配失败\n");
        return 1;
    }

    for (int i = 0; i < n; i++) {
        if (scanf("%d", &a[i]) != 1) {
            fprintf(stderr, "输入不足：需要 %d 个整数\n", n);
            free(a);
            return 1;
        }
    }

    bubble_sort(a, n);

    for (int i = 0; i < n; i++) {
        if (i) putchar(' ');
        printf("%d", a[i]);
    }
    putchar('\n');

    free(a);
    return 0;
}

