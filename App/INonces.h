#ifndef INONCES_H
#define INONCES_H

#include <map>

#include "INonce.h"

#include "salticidae/stream.h"


class INonces {
  private:
    std::map<PID,INonce> inonces;

  public:
    INonces();
    INonces(salticidae::DataStream &data);

    void serialize(salticidae::DataStream &data) const;
    void unserialize(salticidae::DataStream &data);

    std::string prettyPrint();
    std::string toString();

    INonce get(unsigned int i);
    void set(INonce inonce);
    void reset();
    unsigned int size();

    bool operator<(const INonces& s) const;
    bool operator==(const INonces& s) const;
};


#endif
