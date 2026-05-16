// Per-language starter code for the Monaco editor.
// Each snippet is picked to demo stdin handling plus a small loop, so a
// first-time user can hit Run and immediately see something happen.
export const STARTER_CODE = {
  cpp: `#include <iostream>
using namespace std;

int main() {
    string name;
    // Type a name in the stdin box below!
    cin >> name;
    cout << "Hello " << name << "!" << endl;

    for (int i = 1; i <= 5; i++) {
        cout << "Count: " << i << endl;
    }
    return 0;
}`,
  java: `public class Main {
    public static void main(String[] args) {
        java.util.Scanner sc = new java.util.Scanner(System.in);
        String name = sc.hasNext() ? sc.next() : "World";
        System.out.println("Hello " + name + "!");
        for (int i = 1; i <= 5; i++) {
            System.out.println("Count: " + i);
        }
    }
}`,
  python: `import sys

name = sys.stdin.readline().strip() or "World"
print(f"Hello {name}!")
for i in range(1, 6):
    print(f"Count: {i}")`,
  typescript: `const name: string = (await new Promise<string>((resolve) => {
  let buf = "";
  process.stdin.on("data", (c) => (buf += c));
  process.stdin.on("end", () => resolve(buf.trim() || "World"));
})) as string;

console.log(\`Hello \${name}!\`);
for (let i = 1; i <= 5; i++) console.log(\`Count: \${i}\`);`,
};
