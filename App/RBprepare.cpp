#include "RBprepare.h"
#include <iostream>


RBprepare::RBprepare() {
  this->session = 0;
  this->view    = 0;
  this->hash    = Hash(false);
}

RBprepare::RBprepare(Session session, View view, Hash hash) {
  this->session = session;
  this->view    = view;
  this->hash    = hash;
}

Session RBprepare::getSession() { return this->session; }
View    RBprepare::getView()    { return this->view;    }
Hash    RBprepare::getHash()    { return this->hash;    }


void RBprepare::serialize(salticidae::DataStream &data) const {
  //unsigned int foo = 101;
  data << this->session << this->view << this->hash;
}


void RBprepare::unserialize(salticidae::DataStream &data) {
  //unsigned int foo;
  data >> this->session >> this->view >> this->hash;
  //if (DEBUG) { std::cout << KLGRN << "unserializing prep: " << foo << KNRM << std::endl; }
}


/*
void RBprepare::insert(OPstore store) {
  if (this->auths.getSize() == 0) {
    this->view = store.getView();
    this->hash = store.getHash();
    this->v = store.getV();
    this->auths.add(store.getAuth());
  } else if (this->view == store.getView() && this->hash == store.getHash() && this->v == getV()) {
    this->auths.add(store.getAuth());
  } else {
    if (DEBUG1) std::cout << KBLU << "RBprepare-insert-C:"
                          << (this->view == store.getView())
                          << ";" << (this->hash == store.getHash())
                          << ";" << this->hash.toString()
                          << ";" << store.getHash().toString()
                          << ";" << (this->v == getV())
                          << KNRM << std::endl;
  }
}
*/

std::string RBprepare::prettyPrint() {
  return ("PREPARE[" + std::to_string(this->session)
          + "," + std::to_string(this->view)
          + "," + (this->hash).prettyPrint()
          + "]");
}

std::string RBprepare::toString() {
  return (std::to_string(this->session)
          + std::to_string(this->view)
          + (this->hash).toString());
}

std::string RBprepare::data() {
  return toString();
}

bool RBprepare::operator<(const RBprepare& s) const {
  return ((session < s.session)
          || (session == s.session && view < s.view));
}

bool RBprepare::operator==(const RBprepare& s) const {
  return (session == s.session
          && view == s.view
          && hash == s.hash);
}
