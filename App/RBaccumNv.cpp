#include "RBaccumNv.h"
#include <iostream>


RBaccumNv::RBaccumNv() {
  this->session = 0;
  this->view    = 0;
  this->prepv   = 0;
  this->hash    = Hash(false);
}

RBaccumNv::RBaccumNv(Session session, View view, View prepv, Hash hash) {
  this->session = session;
  this->view    = view;
  this->prepv   = prepv;
  this->hash    = hash;
}

Session RBaccumNv::getSession() { return this->session; }
View    RBaccumNv::getView()    { return this->view;    }
View    RBaccumNv::getPrepv()   { return this->prepv;   }
Hash    RBaccumNv::getHash()    { return this->hash;    }


void RBaccumNv::serialize(salticidae::DataStream &data) const {
  data << this->session << this->view << this->prepv << this->hash;
}


void RBaccumNv::unserialize(salticidae::DataStream &data) {
  data >> this->session >> this->view >> this->prepv >> this->hash;
}


/*
void RBaccumNv::insert(OPstore store) {
  if (this->auths.getSize() == 0) {
    this->view = store.getView();
    this->hash = store.getHash();
    this->v = store.getV();
    this->auths.add(store.getAuth());
  } else if (this->view == store.getView() && this->hash == store.getHash() && this->v == getV()) {
    this->auths.add(store.getAuth());
  } else {
    if (DEBUG1) std::cout << KBLU << "RBaccumNv-insert-C:"
                          << (this->view == store.getView())
                          << ";" << (this->hash == store.getHash())
                          << ";" << this->hash.toString()
                          << ";" << store.getHash().toString()
                          << ";" << (this->v == getV())
                          << KNRM << std::endl;
  }
}
*/

std::string RBaccumNv::prettyPrint() {
  return ("ACCUM[" + std::to_string(this->session)
          + "," + std::to_string(this->view)
          + "," + std::to_string(this->prepv)
          + "," + (this->hash).prettyPrint()
          + "]");
}

std::string RBaccumNv::toString() {
  return (std::to_string(this->session)
          + std::to_string(this->view)
          + std::to_string(this->prepv)
          + (this->hash).toString());
}

std::string RBaccumNv::data() {
  return (std::to_string(this->session)
          + std::to_string(this->view)
          + std::to_string(this->prepv)
          + (this->hash).toString());
}

bool RBaccumNv::operator<(const RBaccumNv& s) const {
  return ((session < s.session)
          || (session == s.session && view < s.view)
          || (session == s.session && view == s.view && prepv < s.prepv));
}

bool RBaccumNv::operator==(const RBaccumNv& s) const {
  return (session == s.session
          && view == s.view
          && prepv == s.prepv
          && hash == s.hash);
}
