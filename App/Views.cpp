#include <stdio.h>
#include <stdlib.h>
#include <iostream>

#include "Views.h"

void Views::serialize(salticidae::DataStream &data) const {
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    data << this->views[i];
  }
}

void Views::unserialize(salticidae::DataStream &data) {
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    data >> this->views[i];
  }
}

Views::Views(View views[MAX_NUM_NODES]) {
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    this->views[i] = views[i];
  }
}

Views::Views(salticidae::DataStream &data) {
  unserialize(data);
}

Views::Views() {
  for (int i = 0; i < MAX_NUM_NODES; i++) { this->views[i] = 0; }
}

View Views::get(unsigned int n) {
  return this->views[n];
}

std::string Views::prettyPrint() {
  std::string text = "";
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    text += ":" + std::to_string(views[i]);
  }
  return ("VIEWS[-" + text + ":]");
}

std::string Views::toString() {
  std::string text = "";
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    text += std::to_string(views[i]);
  }
  return text;
}


bool Views::operator<(const Views& s) const {
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    if (views[i] < s.views[i]) { return true; }
    if (views[i] > s.views[i]) { return false; }
  }
  return false;
}

bool Views::operator==(const Views& s) const {
  for (int i = 0; i < MAX_NUM_NODES; i++) {
    if (!(views[i] == s.views[i])) { return false; }
  }
  return true;
}
