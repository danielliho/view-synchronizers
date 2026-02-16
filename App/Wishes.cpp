#include <stdio.h>
#include <stdlib.h>
#include <iostream>

#include "Wishes.h"

void Wishes::serialize(salticidae::DataStream &data) const {
  data << this->size;
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    data << this->wishes[i];
  }
}

void Wishes::unserialize(salticidae::DataStream &data) {
  data >> this->size;
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    data >> this->wishes[i];
  }
}

Wishes::Wishes(Wish wish) {
  this->wishes[0] = wish;
  this->size=1;
}

Wishes::Wishes(unsigned int size, Wish wishes[MAX_NUM_NODES]) {
  this->size=size;
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    this->wishes[i] = wishes[i];
  }
}

Wishes::Wishes(salticidae::DataStream &data) {
  unserialize(data);
}

Wishes::Wishes() {
  for (int i = 0; i < MAX_NUM_NODES; i++) { this->wishes[i] = Wish(); }
}

unsigned int Wishes::getSize() {
  return this->size;
}

Wish Wishes::get(unsigned int n) {
  return this->wishes[n];
}

std::string Wishes::prettyPrint() {
  std::string text = "";
  for (int i = 0; i < this->size; i++) {
    text += ":" + wishes[i].prettyPrint();
  }
  return ("WISHES[-" + std::to_string(this->size) + "-" + text + ":]");
}

std::string Wishes::toString() {
  std::string text = std::to_string(this->size);
  for (int i = 0; i < this->size; i++) {
    text += wishes[i].toString();
  }
  return text;
}


bool Wishes::operator<(const Wishes& s) const {
  if (size < s.size) { return true; }
  if (s.size < size) { return false; }
  // They must have the same acutal size
  for (int i = 0; i < size; i++) {
    if (wishes[i] < s.wishes[i]) { return true; }
    if (s.wishes[i] < wishes[i]) { return false; }
  }
  return false;
}

std::set<PID> Wishes::getWishers() {
  std::set<PID> s;
  for (int i = 0; i < this->size; i++) {
    s.insert(this->wishes[i].getAuth().getId());
  }
  return s;
}

std::string Wishes::printWishers() {
  std::string s = "-";
  for (int i = 0; i < this->size; i++) {
    s += this->wishes[i].getAuth().getId() + "-";
  }
  return s;
}

void Wishes::add(Wish wish) {
  this->wishes[this->size]=wish;
  this->size++;
}

void Wishes::addUpto(Wishes others, unsigned int n) {
  for (int i = 0; i < others.getSize() && this->size < n; i++) {
    this->add(others.get(i));
  }
}

bool Wishes::operator==(const Wishes& s) const {
  if (this->size != s.size) { return false; }
  for (int i = 0; i < MAX_NUM_NODES && i < this->size; i++) { if (!(wishes[i] == s.wishes[i])) { return false; } }
  return true;
}
