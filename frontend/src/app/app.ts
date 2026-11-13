import { Component } from '@angular/core';
import { GraphComponent } from './graph.component';

@Component({
  selector: 'app-root',
  imports: [GraphComponent],
  template: '<app-graph />',
})
export class App {}
