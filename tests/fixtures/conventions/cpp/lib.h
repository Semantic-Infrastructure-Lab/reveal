#pragma once
#include <vector>
#include <boost/optional.hpp>

class Lib {
public:
    Lib();
    ~Lib();
    int used() const;
    int orphan() const;
    bool operator==(const Lib &o) const;
    const std::vector<int> &items() const;
private:
    std::vector<int> v;
};
