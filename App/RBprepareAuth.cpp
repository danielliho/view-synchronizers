#include "RBprepareAuth.h"
#include <iostream>


RBprepareAuth::RBprepareAuth() {
  this->prep = RBprepare();
  this->auth = Auth();
}

RBprepareAuth::RBprepareAuth(RBprepare prepare, Auth auth) {
  this->prep = prepare;
  this->auth = auth;
}

RBprepare RBprepareAuth::getPrepare() { return this->prep; }
Auth      RBprepareAuth::getAuth()    { return this->auth; }


void RBprepareAuth::serialize(salticidae::DataStream &data) const {
  data << this->prep << this->auth;
}


void RBprepareAuth::unserialize(salticidae::DataStream &data) {
  data >> this->prep >> this->auth;
}


/*
void RBprepareAuth::insert(OPstore store) {
  if (this->auths.getSize() == 0) {
    this->view = store.getView();
    this->hash = store.getHash();
    this->v = store.getV();
    this->auths.add(store.getAuth());
  } else if (this->view == store.getView() && this->hash == store.getHash() && this->v == getV()) {
    this->auths.add(store.getAuth());
  } else {
    if (DEBUG1) std::cout << KBLU << "RBprepareAuth-insert-C:"
                          << (this->view == store.getView())
                          << ";" << (this->hash == store.getHash())
                          << ";" << this->hash.toString()
                          << ";" << store.getHash().toString()
                          << ";" << (this->v == getV())
                          << KNRM << std::endl;
  }
}
*/

std::string RBprepareAuth::prettyPrint() {
  return ("PREPARE-AUTH[" + (this->prep).prettyPrint()
          + "," + (this->auth).prettyPrint() + "]");
}

std::string RBprepareAuth::toString() {
  return ((this->prep).toString()
          + (this->auth).toString());
}

std::string RBprepareAuth::data() {
  return ((this->prep).toString()
          + (this->auth).toString());
}

bool RBprepareAuth::operator<(const RBprepareAuth& s) const {
  return ((prep < s.prep)
          || ((prep == s.prep && auth < s.auth)));
}
