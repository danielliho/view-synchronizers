#include "RBnewviewAuth.h"
#include <iostream>


RBnewviewAuth::RBnewviewAuth() {
  this->newview = RBnewview();
  this->auth    = Auth();
}

RBnewviewAuth::RBnewviewAuth(RBnewview newview, Auth auth) {
  this->newview = newview;
  this->auth    = auth;
}

RBnewview RBnewviewAuth::getNewview() { return this->newview; }
Auth      RBnewviewAuth::getAuth()    { return this->auth;    }


void RBnewviewAuth::serialize(salticidae::DataStream &data) const {
  data << this->newview << this->auth;
}


void RBnewviewAuth::unserialize(salticidae::DataStream &data) {
  data >> this->newview >> this->auth;
}


/*
void RBnewviewAuth::insert(OPstore store) {
  if (this->auths.getSize() == 0) {
    this->view = store.getView();
    this->hash = store.getHash();
    this->v = store.getV();
    this->auths.add(store.getAuth());
  } else if (this->view == store.getView() && this->hash == store.getHash() && this->v == getV()) {
    this->auths.add(store.getAuth());
  } else {
    if (DEBUG1) std::cout << KBLU << "RBnewviewAuth-insert-C:"
                          << (this->view == store.getView())
                          << ";" << (this->hash == store.getHash())
                          << ";" << this->hash.toString()
                          << ";" << store.getHash().toString()
                          << ";" << (this->v == getV())
                          << KNRM << std::endl;
  }
}
*/

std::string RBnewviewAuth::prettyPrint() {
  return ("NEWVIEW-AUTH[" + (this->newview).prettyPrint()
          + "," + (this->auth).prettyPrint() + "]");
}

std::string RBnewviewAuth::toString() {
  return ((this->newview).toString()
          + (this->auth).toString());
}

std::string RBnewviewAuth::data() {
  return ((this->newview).toString()
          + (this->auth).toString());
}

bool RBnewviewAuth::operator==(const RBnewviewAuth& s) const {
  return (newview == s.newview && auth == s.auth);
}

bool RBnewviewAuth::operator<(const RBnewviewAuth& s) const {
  return ((newview < s.newview)
          || ((newview == s.newview && auth < s.auth)));
}
