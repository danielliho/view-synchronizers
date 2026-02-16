#include "Sync.h"

bool Sync::operator<(const Sync& s) const {
  return (session < s.session
          || (session == s.session && view < s.view)
          || (session == s.session && view == s.view && auth < s.auth));
}

void Sync::serialize(salticidae::DataStream &data) const {
  data << this->session << this->view << this->block << this->auth;
}

void Sync::unserialize(salticidae::DataStream &data) {
  data >> this->session >> this->view >> this->block >> this->auth;
}

Sync::Sync() {
  this->session = 0;
  this->view    = 0;
  this->block   = Hash(false);
  this->auth    = Auth(false);
}

Sync::Sync(Session session, View view, Hash block, Auth auth) {
  this->session = session;
  this->view    = view;
  this->block   = block;
  this->auth    = auth;
}

std::string Sync::toString() {
  std::string s = (std::to_string(this->session)
                   + std::to_string(this->view)
                   + this->block.toString()
                   + this->auth.toString());
  return s;
}

std::string Sync::prettyPrint() {
  return "SYNC[" + std::to_string(this->session)
    + "," + std::to_string(this->view)
    + "," + this->block.prettyPrint()
    + "," + this->auth.prettyPrint()
    + "]";
}

Session Sync::getSession() { return this->session; }
View    Sync::getView()    { return this->view;    }
Hash    Sync::getBlock()   { return this->block;   }
Auth    Sync::getAuth()    { return this->auth;    }

bool Sync::operator==(const Sync& s) const {
  return (this->session == s.session
          && this->view == s.view
          && this->block == s.block
          && this->auth == s.auth);
}
