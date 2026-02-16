#include <stdio.h>
#include <stdlib.h>
#include <iostream>

#include "VJoins.h"

void VJoins::serialize(salticidae::DataStream &data) const {
  data << this->from << this->to << this->joins << this->views;
}

void VJoins::unserialize(salticidae::DataStream &data) {
  data >> this->from >> this->to >> this->joins >> this->views;
}

VJoins::VJoins(View from, View to, Joins joins, Views views) {
  this->from  = from;
  this->to    = to;
  this->joins = joins;
  this->views = views;
}

VJoins::VJoins(salticidae::DataStream &data) {
  unserialize(data);
}

VJoins::VJoins() {}

View  VJoins::getFrom()  { return this->from; }
View  VJoins::getTo()    { return this->to; }
Joins VJoins::getJoins() { return this->joins; }
Views VJoins::getViews() { return this->views; }

std::string VJoins::prettyPrint() {
  return ("VJOINS[-"
          + std::to_string(this->from)
          + "-" + std::to_string(this->to)
          + "-" + this->joins.prettyPrint()
          + "-" + this->views.prettyPrint()
          + ":]");
}

std::string VJoins::toString() {
  return (std::to_string(this->from) + std::to_string(this->to) + this->joins.toString() + this->views.toString());
}


bool VJoins::operator<(const VJoins& s) const {
  if (from < s.from) { return true; }
  if (from == s.from) {
    if (to < s.to) { return true; }
    if (to == s.to) {
      if (joins < s.joins) { return true; }
      if (joins == s.joins) {
        return (views < s.views);
      }
      return false;
    }
    return false;
  }
  return false;
}

bool VJoins::operator==(const VJoins& s) const {
  return (this->from == s.from && this->to == s.to && this->joins == s.joins && this->views == s.views);
}
