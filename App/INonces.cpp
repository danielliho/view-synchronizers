#include <stdio.h>
#include <stdlib.h>
#include <iostream>
#include <set>

#include "INonces.h"

unsigned int INonces::size() { return this->inonces.size(); }

void INonces::serialize(salticidae::DataStream &data) const {
  unsigned int size = this->inonces.size();
  data << size;
  for (std::map<PID,INonce>::const_iterator it = this->inonces.begin(); it != this->inonces.end(); it++) {
    INonce nonce = (INonce)it->second;
    data << nonce;
  }
}

void INonces::unserialize(salticidae::DataStream &data) {
  unsigned int size;
  data >> size;
  std::set<PID> ids;
  for (int i = 0; i < size; i++) {
    INonce nonce;
    data >> nonce;
    this->inonces[nonce.getId()] = nonce;
  }
}

INonces::INonces(salticidae::DataStream &data) {
  unserialize(data);
}

void INonces::reset() {
  this->inonces.erase(this->inonces.begin(),this->inonces.end());
}

INonces::INonces() { reset(); }

INonce INonces::get(unsigned int n) {
  if (this->inonces.find(n) != this->inonces.end()) {
    return this->inonces[n];
  }
  return INonce();
}

void INonces::set(INonce inonce) {
  PID id = inonce.getId();
  if (inonce.getNonce().getSet()) { this->inonces[id] = inonce; }
}

std::string INonces::prettyPrint() {
  std::string text = "";
  for (std::map<PID,INonce>::iterator it = this->inonces.begin(); it != this->inonces.end(); it++) {
    text += ":" + (it->second).prettyPrint();
  }
  return ("INONCES[" + text + ":]");
}

std::string INonces::toString() {
  std::string text = "";
  for (std::map<PID,INonce>::iterator it = this->inonces.begin(); it != this->inonces.end(); it++) {
    text += (it->second).toString();
  }
  return text;
}

bool INonces::operator<(const INonces& s) const {
  return (this->inonces < s.inonces);
}

bool INonces::operator==(const INonces& s) const {
  return (this->inonces == s.inonces);
}
