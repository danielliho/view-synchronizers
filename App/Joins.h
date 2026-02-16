#ifndef JOINS_H
#define JOINS_H

#include <map>

#include "Join.h"

#include "salticidae/stream.h"


class Joins {
  private:
    std::map<PID,Join> joins;

  public:
    Joins();
    Joins(salticidae::DataStream &data);

    void serialize(salticidae::DataStream &data) const;
    void unserialize(salticidae::DataStream &data);

    std::string prettyPrint();
    std::string toString();

    Join get(unsigned int i);
    void set(Join join);
    void del(unsigned int i);
    bool in(unsigned int i);
    void reset();
    unsigned int size();

    Hash hash();

    void add(Joins joins);

    bool operator<(const Joins& s) const;
    bool operator==(const Joins& s) const;
};


#endif
