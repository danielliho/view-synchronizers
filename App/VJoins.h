#ifndef VJOINS_H
#define VJOINS_H

#include <set>

#include "Hash.h"
#include "Joins.h"
#include "Views.h"

#include "salticidae/stream.h"


class VJoins {
  private:
    View from = 0;
    View to   = 0;
    Joins joins;
    Views views;

  public:
    VJoins();
    VJoins(View from, View to, Joins joins, Views views);
    VJoins(salticidae::DataStream &data);

    void serialize(salticidae::DataStream &data) const;
    void unserialize(salticidae::DataStream &data);

    std::string prettyPrint();
    std::string toString();

    View getFrom();
    View getTo();
    Joins getJoins();
    Views getViews();

    bool operator<(const VJoins& s) const;
    bool operator==(const VJoins& s) const;
};


#endif
