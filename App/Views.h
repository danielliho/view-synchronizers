#ifndef VIEWS_H
#define VIEWS_H

#include "params.h"
#include "types.h"

#include "salticidae/stream.h"


class Views {
  private:
    View views[MAX_NUM_NODES];

  public:
    Views();
    Views(View views[MAX_NUM_NODES]);
    Views(salticidae::DataStream &data);

    void serialize(salticidae::DataStream &data) const;
    void unserialize(salticidae::DataStream &data);

    std::string prettyPrint();
    std::string toString();

    View get(unsigned int i);

    bool operator<(const Views& s) const;
    bool operator==(const Views& s) const;
};


#endif
