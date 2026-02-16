#ifndef PM_SYNCS_H
#define PM_SYNCS_H

#include "types.h"
#include "config.h"
#include "Hash.h"
#include "Auths.h"

#include "salticidae/stream.h"


class PmSyncs {

 private:
  View view;
  Hash block; // hash of the last prepared block
  Auths auths;

 public:
  PmSyncs();
  PmSyncs(View view, Hash block, Auth auth);
  PmSyncs(View view, Hash block, Auths auths);

  View  getView();
  Hash  getBlock();
  Auths getAuths();

  void add(Auth auth);

  void serialize(salticidae::DataStream &data) const;
  void unserialize(salticidae::DataStream &data);

  std::string toString();
  std::string prettyPrint();

  bool operator<(const PmSyncs& s) const;
  bool operator==(const PmSyncs& s) const;
};

#endif
