#ifndef WISHES_H
#define WISHES_H

#include <set>

#include "Hash.h"
#include "Wish.h"

#include "salticidae/stream.h"


class Wishes {
  private:
    unsigned int size = 0;
    Wish wishes[MAX_NUM_NODES];

  public:
    Wishes();
    Wishes(Wish wish);
    Wishes(unsigned int size, Wish wishes[MAX_NUM_NODES]);
    Wishes(salticidae::DataStream &data);

    void serialize(salticidae::DataStream &data) const;
    void unserialize(salticidae::DataStream &data);

    std::string prettyPrint();
    std::string toString();

    unsigned int getSize();
    Wish get(unsigned int i);
    std::set<PID> getWishers();
    void add(Wish wish);
    void addUpto(Wishes others, unsigned int n);
    std::string printWishers();

    bool operator<(const Wishes& s) const;
    bool operator==(const Wishes& s) const;
};


#endif
