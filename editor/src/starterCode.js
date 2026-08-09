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
  java: `public class Main {
    public static void main(String[] args) {
        String name= IO.readln();
        IO.println("Hello " + name + "!");
    }
}`,
  python: `name = input()
print(f"Hello {name}!")`,
};
