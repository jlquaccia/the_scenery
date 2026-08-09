import { TestBed } from '@angular/core/testing';

import { App } from './app';

describe('App shell', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({ imports: [App] }).compileComponents();
  });

  it('renders both panes', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const shell = fixture.nativeElement as HTMLElement;

    expect(shell.querySelector('app-map-pane')).toBeTruthy();
    expect(shell.querySelector('app-chat-pane')).toBeTruthy();
  });

  it('labels the panes for assistive tech', async () => {
    const fixture = TestBed.createComponent(App);
    await fixture.whenStable();
    const labels = Array.from(
      (fixture.nativeElement as HTMLElement).querySelectorAll('section[aria-label]'),
    ).map((el) => el.getAttribute('aria-label'));

    expect(labels).toEqual(['Scene map', 'Chat']);
  });
});
