#ifndef PM_SYNC_H
#define PM_SYNC_H

#include "types.h"
#include "config.h"
#include "Hash.h"
#include "Auth.h"

#include "salticidae/stream.h"


class PmSync {

 private:
  View view;
  Hash block; // hash of the last prepared block
  Auth auth;

 public:
  PmSync();
  PmSync(View view, Hash block, Auth auth);

  View getView();
  Hash getBlock();
  Auth getAuth();

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string toString();
  std::string prettyPrint();

  bool operator<(const PmSync& s) const;
  bool operator==(const PmSync& s) const;
};

#endif
