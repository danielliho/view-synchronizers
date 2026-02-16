#ifndef RBNEWVIEW_H
#define RBNEWVIEW_H


#include "config.h"
#include "types.h"
#include "Hash.h"


#include "salticidae/stream.h"


class RBnewview {
 private:
  Session session = 0;
  View    view    = 0;
  View    prepv   = 0;
  Hash    hash;

 public:
  RBnewview(Session session, View view, View prepv, Hash hash);
  RBnewview(salticidae::DataStream &data);
  RBnewview();

  Session getSession();
  View    getView();
  View    getPrepv();
  Hash    getHash();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();

  bool operator==(const RBnewview& s) const;
  bool operator<(const RBnewview& s) const;
};


#endif
