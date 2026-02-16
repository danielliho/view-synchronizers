#include <stdio.h>
#include <stdlib.h>
#include <iostream>

#include "Joins.h"

unsigned int Joins::size() { return this->joins.size(); }

void Joins::serialize(salticidae::DataStream &data) const {
  unsigned int size = this->joins.size();
  data << size;
  if (DEBUG5) { std::cout << KLGRN << "serializing " << size << " joins" << KNRM << std::endl; }
  for (std::map<PID,Join>::const_iterator it = this->joins.begin(); it != this->joins.end(); it++) {
    Join join = (Join)it->second;
    if (DEBUG5) { std::cout << KLGRN << "serializing a join: " << join.prettyPrint() << KNRM << std::endl; }
    data << join;
  }
}

void Joins::unserialize(salticidae::DataStream &data) {
  unsigned int size;
  data >> size;
  if (DEBUG5) { std::cout << KLGRN << "unserializing " << size << " joins" << KNRM << std::endl; }
  for (int i = 0; i < size; i++) {
    Join join;
    data >> join;
    PID id = join.getAuth().getId();
    this->joins[id] = join;
    if (DEBUG5) { std::cout << KLGRN << "unserializing a join " << join.prettyPrint() << KNRM << std::endl; }
  }
}

Joins::Joins(salticidae::DataStream &data) {
  unserialize(data);
}

void Joins::reset() {
  this->joins.erase(this->joins.begin(),this->joins.end());
}

Joins::Joins() { reset(); }

Join Joins::get(unsigned int n) {
  if (this->joins.find(n) != this->joins.end()) {
    return this->joins[n];
  }
  return Join();
}

void Joins::set(Join join) {
  PID id = join.getAuth().getId();
  if (join.getNonce().getSet()) { this->joins[id] = join; }
}

void Joins::del(unsigned int i) {
  this->joins.erase(i);
}

bool Joins::in(unsigned int i) {
  return (this->joins.find(i) != this->joins.end());
}

std::string Joins::prettyPrint() {
  std::string text = "";
  for (std::map<PID,Join>::iterator it = this->joins.begin(); it != this->joins.end(); it++) {
    text += ":" + (it->second).prettyPrint();
  }
  return ("JOINS[" + text + ":]");
}


std::string Joins::toString() {
  std::string text = "";
  for (std::map<PID,Join>::iterator it = this->joins.begin(); it != this->joins.end(); it++) {
    text += (it->second).toString();
  }
  return text;
}


Hash Joins::hash() {
  unsigned char h[SHA256_DIGEST_LENGTH];
  std::string text = this->toString();

  if (!SHA256 ((const unsigned char *)text.c_str(), text.size(), h)){
    std::cout << KCYN << "SHA1 failed" << KNRM << std::endl;
    exit(0);
  }
  return Hash(h);
}

void Joins::add(Joins js) {
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    if (js.get(i).getNonce().getSet() && !(get(i).getNonce().getSet())) {
      set(js.get(i));
    }
  }
}

bool Joins::operator<(const Joins& s) const {
  return (this->joins < s.joins);
}

bool Joins::operator==(const Joins& s) const {
  return (this->joins == s.joins);
}
