#ifndef RBPROPOSAL_H
#define RBPROPOSAL_H

#include "RBaccumNvAuth.h"

#include "salticidae/stream.h"

class RBproposal {

 private:
  Hash          block;
  RBaccumNvAuth acc;

 public:
  RBproposal();
  RBproposal(Hash block, RBaccumNvAuth acc);

  Hash          getBlock();
  RBaccumNvAuth getAcc();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string prettyPrint();
  std::string toString();

  bool operator<(const RBproposal& s) const;
  bool operator==(const RBproposal& s) const;
};


#endif
