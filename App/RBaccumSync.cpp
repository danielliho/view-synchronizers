#include "RBaccumSync.h"
#include <iostream>


RBaccumSync::RBaccumSync() {
  this->session = 0;
  this->view    = 0;
  this->hash    = Hash(false);
}

RBaccumSync::RBaccumSync(Session session, View view, Hash hash) {
  this->session = session;
  this->view    = view;
  this->hash    = hash;
}

Session RBaccumSync::getSession() { return this->session; }
View    RBaccumSync::getView()    { return this->view;    }
Hash    RBaccumSync::getHash()    { return this->hash;    }


void RBaccumSync::serialize(salticidae::DataStream &data) const {
  data << this->session << this->view << this->hash;
}


void RBaccumSync::unserialize(salticidae::DataStream &data) {
  data >> this->session >> this->view >> this->hash;
}


/*
void RBaccumSync::insert(OPstore store) {
  if (this->auths.getSize() == 0) {
    this->view = store.getView();
    this->hash = store.getHash();
    this->v = store.getV();
    this->auths.add(store.getAuth());
  } else if (this->view == store.getView() && this->hash == store.getHash() && this->v == getV()) {
    this->auths.add(store.getAuth());
  } else {
    if (DEBUG1) std::cout << KBLU << "RBaccumSync-insert-C:"
                          << (this->view == store.getView())
                          << ";" << (this->hash == store.getHash())
                          << ";" << this->hash.toString()
                          << ";" << store.getHash().toString()
                          << ";" << (this->v == getV())
                          << KNRM << std::endl;
  }
}
*/

std::string RBaccumSync::prettyPrint() {
  return ("ACCUM[" + std::to_string(this->session)
          + "," + std::to_string(this->view)
          + "," + (this->hash).prettyPrint()
          + "]");
}

std::string RBaccumSync::toString() {
  return (std::to_string(this->session)
          + std::to_string(this->view)
          + (this->hash).toString());
}

std::string RBaccumSync::data() {
  return (std::to_string(this->session)
          + std::to_string(this->view)
          + (this->hash).toString());
}

bool RBaccumSync::operator<(const RBaccumSync& s) const {
  return ((session < s.session)
          || (session == s.session && view < s.view));
}

bool RBaccumSync::operator==(const RBaccumSync& s) const {
  return (session == s.session
          && view == s.view
          && hash == s.hash);
}
