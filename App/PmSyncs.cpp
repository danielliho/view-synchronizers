#include "PmSyncs.h"

bool PmSyncs::operator<(const PmSyncs& s) const {
  return (view < s.view
          || (view == s.view && auths < s.auths));
}

void PmSyncs::serialize(salticidae::DataStream &data) const {
  data << this->view << this->block << this->auths;
}

void PmSyncs::unserialize(salticidae::DataStream &data) {
  data >> this->view >> this->block >> this->auths;
}

PmSyncs::PmSyncs() {
  this->view  = 0;
  this->block = Hash(false);
  this->auths = Auths();
}

PmSyncs::PmSyncs(View view, Hash block, Auths auths) {
  this->view  = view;
  this->block = block;
  this->auths = auths;
}

PmSyncs::PmSyncs(View view, Hash block, Auth auth) {
  this->view  = view;
  this->block = block;
  this->auths = Auths(auth);
}

void PmSyncs::add(Auth auth) {
  this->auths.add(auth);
}

std::string PmSyncs::toString() {
  std::string s = (std::to_string(this->view)
                   + this->block.toString()
                   + this->auths.toString());
  return s;
}

std::string PmSyncs::prettyPrint() {
  return "SYNC[" + std::to_string(this->view)
    + "," + this->block.prettyPrint()
    + "," + this->auths.prettyPrint() + "]";
}

View  PmSyncs::getView()  { return this->view;  }
Hash  PmSyncs::getBlock() { return this->block; }
Auths PmSyncs::getAuths() { return this->auths; }

bool PmSyncs::operator==(const PmSyncs& s) const {
  return (this->view == s.view && this->block == s.block && this->auths == s.auths);
}
