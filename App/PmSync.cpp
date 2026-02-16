#include "PmSync.h"

bool PmSync::operator<(const PmSync& s) const {
  return (view < s.view
          || (view == s.view && auth < s.auth));
}

void PmSync::serialize(salticidae::DataStream &data) const {
  data << this->view << this->block << this->auth;
}

void PmSync::unserialize(salticidae::DataStream &data) {
  data >> this->view >> this->block >> this->auth;
}

PmSync::PmSync() {
  this->view  = 0;
  this->block = Hash(false);
  this->auth  = Auth(false);
}

PmSync::PmSync(View view, Hash block, Auth auth) {
  this->view  = view;
  this->block = block;
  this->auth  = auth;
}

std::string PmSync::toString() {
  std::string s = (std::to_string(this->view)
                   + this->block.toString()
                   + this->auth.toString());
  return s;
}

std::string PmSync::prettyPrint() {
  return "SYNC[" + std::to_string(this->view)
    + "," + this->block.prettyPrint()
    + "," + this->auth.prettyPrint() + "]";
}

View PmSync::getView()    { return this->view;  }
Hash PmSync::getBlock()   { return this->block; }
Auth PmSync::getAuth()    { return this->auth;  }

bool PmSync::operator==(const PmSync& s) const {
  return (this->view == s.view && this->block == s.block && this->auth == s.auth);
}
