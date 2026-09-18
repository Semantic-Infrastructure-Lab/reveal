import fs from "fs";
import React from 'react';

function used(): Buffer {
  return fs.readFileSync('x');
}

function orphan() {
  return React.version;
}

class Ctl {
  @Get()
  index() {}
}
