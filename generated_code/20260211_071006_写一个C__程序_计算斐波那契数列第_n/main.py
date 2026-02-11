```cpp
#include <iostream>

long long fibonacci(int n) {
    if (n <= 1) return n;
    
    long long a = 0, b = 1;
    for (int i = 2; i <= n; i++) {
        long long temp = a + b;
        a = b;
        b = temp;
    }
    return b;
}

int main() {
    int n;
    std::cout << "请输入要计算的斐波那契数列项数 n: ";
    std::cin >> n;
    
    if (n < 0) {
        std::cout << "请输入非负整数！" << std::endl;
        return 1;
    }
    
    std::cout << "斐波那契数列第 " << n << " 项是: " << fibonacci(n) << std::endl;
    return 0;
}
```