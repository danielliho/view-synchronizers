#ifndef RBACCUMNV_H
#define RBACCUMNV_H

#include "Hash.h"

#include "salticidae/stream.h"

// an accumulator (rollback prevention)
class RBaccumNv {

 private:
  Session session;
  View    view; // View at which the certifiate was created
  View    prepv;
  Hash    hash;

 public:
  RBaccumNv();
  RBaccumNv(Session session, View view, View prepv, Hash hash);

  Session  getSession();
  View     getView();
  View     getPrepv();
  Hash     getHash();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();
  std::string data();

  bool operator<(const RBaccumNv& s) const;
  bool operator==(const RBaccumNv& s) const;
};


#endif
