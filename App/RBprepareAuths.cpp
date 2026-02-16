#include "RBprepareAuths.h"
#include <iostream>


RBprepareAuths::RBprepareAuths() {
  this->prep  = RBprepare();
  this->auths = Auths();
}

RBprepareAuths::RBprepareAuths(RBprepare prep, Auths auths) {
  this->prep  = prep;
  this->auths = auths;
}

RBprepare RBprepareAuths::getPrepare() { return this->prep;  }
Auths     RBprepareAuths::getAuths()   { return this->auths; }


void RBprepareAuths::serialize(salticidae::DataStream &data) const {
  data << this->prep << this->auths;
}


void RBprepareAuths::unserialize(salticidae::DataStream &data) {
  data >> this->prep >> this->auths;
}


void RBprepareAuths::add(Auth a) {
  this->auths.add(a);
}

/*
void RBprepareAuths::insert(OPstore store) {
  if (this->auths.getSize() == 0) {
    this->view = store.getView();
    this->hash = store.getHash();
    this->v = store.getV();
    this->auths.add(store.getAuth());
  } else if (this->view == store.getView() && this->hash == store.getHash() && this->v == getV()) {
    this->auths.add(store.getAuth());
  } else {
    if (DEBUG1) std::cout << KBLU << "RBprepareAuths-insert-C:"
                          << (this->view == store.getView())
                          << ";" << (this->hash == store.getHash())
                          << ";" << this->hash.toString()
                          << ";" << store.getHash().toString()
                          << ";" << (this->v == getV())
                          << KNRM << std::endl;
  }
}
*/

std::string RBprepareAuths::prettyPrint() {
  return ("PREPARE-AUTHS[" + (this->prep).prettyPrint()
          + "," + (this->auths).prettyPrint() + "]");
}

std::string RBprepareAuths::toString() {
  return ((this->prep).toString()
          + (this->auths).toString());
}

std::string RBprepareAuths::data() {
  return ((this->prep).toString()
          + (this->auths).toString());
}

bool RBprepareAuths::operator<(const RBprepareAuths& s) const {
  if (prep < s.prep) { return true ; }
  if (prep == s.prep) {
    return (auths < s.auths);
  }
  return false;
}
