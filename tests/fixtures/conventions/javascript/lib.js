import fs from 'fs';
import React from 'react';

function used() {
  return fs.readFileSync('x');
}

function orphan() {
  return React.version;
}
