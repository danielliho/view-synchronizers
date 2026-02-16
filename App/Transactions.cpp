#include <stdio.h>
#include <stdlib.h>
#include <iostream>

#include "Transactions.h"

void Transactions::serialize(salticidae::DataStream &data) const {
  data << this->size;
  for (int i = 0; i < MAX_NUM_TRANSACTIONS; i++) {
    data << this->transactions[i];
  }
}

void Transactions::unserialize(salticidae::DataStream &data) {
  data >> this->size;
  for (int i = 0; i < MAX_NUM_TRANSACTIONS; i++) {
    data >> this->transactions[i];
  }
}

Transactions::Transactions(Transaction t) {
  this->transactions[0] = t;
  this->size=1;
}

Transactions::Transactions(unsigned int size, Transaction transactions[MAX_NUM_SIGNATURES]) {
  this->size=size;
  for (int i = 0; i < MAX_NUM_TRANSACTIONS; i++) {
    this->transactions[i] = transactions[i];
  }
}

Transactions::Transactions(salticidae::DataStream &data) {
  unserialize(data);
}

Transactions::Transactions() {
  for (int i = 0; i < MAX_NUM_TRANSACTIONS; i++) { this->transactions[i] = Transaction(); }
}

unsigned int Transactions::getSize() {
  return this->size;
}

Transaction Transactions::get(unsigned int n) {
  return this->transactions[n];
}

std::string Transactions::prettyPrint() {
  std::string text = "";
  for (int i = 0; i < this->size; i++) {
    text += ":" + transactions[i].prettyPrint();
  }
  return ("TRANSACTIONS[-" + std::to_string(this->size) + "-" + text + ":]");
}

std::string Transactions::toString() {
  std::string text = std::to_string(this->size);
  for (int i = 0; i < this->size; i++) {
    text += transactions[i].toString();
  }
  return text;
}


bool Transactions::operator<(const Transactions& s) const {
  if (size < s.size) { return true; }
  if (size == s.size) {
    // They must have the same acutal size
    for (int i = 0; i < size; i++) {
      if (!(transactions[i] < s.transactions[i])) { return false; }
    }
    return true;
  }
  return false;
}

void Transactions::add(Transaction t) {
  this->transactions[this->size]=t;
  this->size++;
}

void Transactions::addUpto(Transactions others, unsigned int n) {
  for (int i = 0; i < others.getSize() && this->size < n; i++) {
    this->add(others.get(i));
  }
}

bool Transactions::operator==(const Transactions& s) const {
  if (this->size != s.size) { return false; }
  for (int i = 0; i < MAX_NUM_TRANSACTIONS && i < this->size; i++) { if (!(transactions[i] == s.transactions[i])) { return false; } }
  return true;
}
