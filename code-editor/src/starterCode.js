// Per-language starter code for the Monaco editor.
// Each snippet reads a single token from stdin and prints "Hello <token>!"
// — minimal so a first run produces obvious output without distractions.
export const STARTER_CODE = {
  cpp: `#include <bits/stdc++.h>
using namespace std;

int main() {
    string name;
    cin >> name;
    cout << "Hello " << name << "!" << endl;
    return 0;
}`,
  java: `import java.util.*;
import java.io.*;

public class Main {
    public static void main(String[] args) {
        Scanner sc = new Scanner(System.in);
        String name = sc.next();
        System.out.println("Hello " + name + "!");
    }
}`,
  python: `name = input()
print(f"Hello {name}!")`,
  typescript: `const name: string = require("fs").readFileSync(0, "utf-8").trim();
console.log(\`Hello \${name}!\`);`,
};
