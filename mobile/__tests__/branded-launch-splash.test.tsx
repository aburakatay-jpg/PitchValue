import { act, render } from '@testing-library/react-native';
import { useEvent, useEventListener } from 'expo';
import * as SplashScreen from 'expo-splash-screen';
import { useVideoPlayer } from 'expo-video';

import {
  BrandedLaunchSplash,
  BrandedSplashVideo,
} from '@/components/BrandedLaunchSplash';

jest.mock('expo', () => ({
  useEvent: jest.fn(() => ({ status: 'readyToPlay' })),
  useEventListener: jest.fn(),
}));
jest.mock('expo-splash-screen', () => ({
  hideAsync: jest.fn().mockResolvedValue(undefined),
}));
jest.mock('expo-status-bar', () => ({ StatusBar: () => null }));
jest.mock('expo-video', () => {
  const React = require('react');
  const { View } = require('react-native');
  return {
    useVideoPlayer: jest.fn((_source, setup) => {
      const player = {
        status: 'readyToPlay',
        muted: false,
        loop: true,
        staysActiveInBackground: true,
        play: jest.fn(),
      };
      setup(player);
      return player;
    }),
    VideoView: (props: object) => React.createElement(View, props),
  };
});

describe('branded launch video', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(useEvent).mockReturnValue({ status: 'readyToPlay' } as never);
  });

  it('loads the approved local asset muted, covered, and without controls', async () => {
    const onFirstFrame = jest.fn();
    const onComplete = jest.fn();
    const view = await render(
      <BrandedSplashVideo
        onComplete={onComplete}
        onFirstFrame={onFirstFrame}
      />,
    );
    const source = require('../assets/splash/pitchvalue-splash.mp4');
    expect(jest.mocked(useVideoPlayer).mock.calls[0]![0]).toBe(source);
    const player = jest.mocked(useVideoPlayer).mock.results[0]!.value;
    expect(player.muted).toBe(true);
    expect(player.loop).toBe(false);
    expect(player.staysActiveInBackground).toBe(false);
    expect(player.play).toHaveBeenCalledTimes(1);
    const video = view.getByTestId('branded-launch-video', {
      includeHiddenElements: true,
    });
    expect(video.props.contentFit).toBe('cover');
    expect(video.props.nativeControls).toBe(false);
    expect(video.props.pointerEvents).toBe('none');
    expect(
      view.getByTestId('branded-launch-splash', { includeHiddenElements: true })
        .props.pointerEvents,
    ).toBe('auto');

    await act(() => video.props.onFirstFrameRender());
    await act(() => video.props.onFirstFrameRender());
    expect(onFirstFrame).toHaveBeenCalledTimes(1);
    const playToEnd = jest
      .mocked(useEventListener)
      .mock.calls.find((call) => call[1] === 'playToEnd')?.[2];
    expect(playToEnd).toBeDefined();
    await act(() => playToEnd?.());
    expect(onComplete).toHaveBeenCalledTimes(1);
    await view.unmount();
  });

  it('fails open on a player error', async () => {
    jest.mocked(useEvent).mockReturnValue({ status: 'error' } as never);
    const onComplete = jest.fn();
    const view = await render(
      <BrandedSplashVideo onComplete={onComplete} onFirstFrame={jest.fn()} />,
    );
    expect(onComplete).toHaveBeenCalledTimes(1);
    await view.unmount();
  });

  it('waits for bootstrap, then reveals the existing app once per process', async () => {
    const view = await render(<BrandedLaunchSplash ready={false} />);
    expect(
      view.queryByTestId('branded-launch-video', {
        includeHiddenElements: true,
      }),
    ).toBeNull();
    expect(SplashScreen.hideAsync).not.toHaveBeenCalled();

    await view.rerender(<BrandedLaunchSplash ready />);
    const video = view.getByTestId('branded-launch-video', {
      includeHiddenElements: true,
    });
    expect(SplashScreen.hideAsync).not.toHaveBeenCalled();
    await act(() => video.props.onFirstFrameRender());
    expect(SplashScreen.hideAsync).toHaveBeenCalledTimes(1);

    const playToEnd = jest
      .mocked(useEventListener)
      .mock.calls.find((call) => call[1] === 'playToEnd')?.[2];
    await act(() => playToEnd?.());
    expect(
      view.queryByTestId('branded-launch-video', {
        includeHiddenElements: true,
      }),
    ).toBeNull();
    await view.rerender(<BrandedLaunchSplash ready />);
    expect(
      view.queryByTestId('branded-launch-video', {
        includeHiddenElements: true,
      }),
    ).toBeNull();
    await view.unmount();

    const nextMount = await render(<BrandedLaunchSplash ready />);
    expect(
      nextMount.queryByTestId('branded-launch-video', {
        includeHiddenElements: true,
      }),
    ).toBeNull();
    await nextMount.unmount();
  });
});
