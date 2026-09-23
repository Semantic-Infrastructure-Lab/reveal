#include "lib.h"

// Constructors, destructors and operators run from declarations, scope exit and
// expression syntax, never a call to their name; main is the runtime entry point.
Lib::Lib() {}
Lib::~Lib() {}
int Lib::used() const { return static_cast<int>(items().size()); }
int Lib::orphan() const { return 0; }
bool Lib::operator==(const Lib &o) const { return true; }
const std::vector<int> &Lib::items() const { return v; }

int main() {
    Lib l;
    return l.used();
}
