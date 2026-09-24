import { useEvent, useEventListener } from 'expo';
import * as SplashScreen from 'expo-splash-screen';
import { useVideoPlayer, VideoView } from 'expo-video';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import { AppState, StyleSheet, View } from 'react-native';

import { darkColors } from '@/theme/tokens';

const splashSource = require('../assets/splash/pitchvalue-splash.mp4');
const failureFallbackMs = 15_000;

let completedInThisProcess = false;

function hideNativeSplash() {
  void SplashScreen.hideAsync().catch(() => {
    // A development host may already have dismissed the native splash.
    try {
      SplashScreen.hide();
    } catch {
      // The app remains mounted even if the host owns native splash state.
    }
  });
}

export function BrandedSplashVideo({
  onFirstFrame,
  onComplete,
}: {
  onFirstFrame: () => void;
  onComplete: () => void;
}) {
  const player = useVideoPlayer(splashSource, (videoPlayer) => {
    videoPlayer.muted = true;
    videoPlayer.loop = false;
    videoPlayer.staysActiveInBackground = false;
  });
  const { status } = useEvent(player, 'statusChange', {
    status: player.status,
  });
  const started = useRef(false);
  const firstFrameShown = useRef(false);

  useEffect(() => {
    if (status === 'error') {
      onComplete();
    } else if (status === 'readyToPlay' && !started.current) {
      started.current = true;
      try {
        player.play();
      } catch {
        onComplete();
      }
    }
  }, [onComplete, player, status]);

  useEventListener(player, 'playToEnd', onComplete);

  useEffect(() => {
    const fallback = setTimeout(onComplete, failureFallbackMs);
    const appState = AppState.addEventListener('change', (nextState) => {
      if (nextState !== 'active') onComplete();
    });
    return () => {
      clearTimeout(fallback);
      appState.remove();
    };
  }, [onComplete]);

  return (
    <View
      accessibilityElementsHidden
      importantForAccessibility="no-hide-descendants"
      pointerEvents="auto"
      style={styles.overlay}
      testID="branded-launch-splash"
    >
      <StatusBar hidden />
      <VideoView
        contentFit="cover"
        nativeControls={false}
        onFirstFrameRender={() => {
          if (firstFrameShown.current) return;
          firstFrameShown.current = true;
          onFirstFrame();
        }}
        player={player}
        pointerEvents="none"
        style={StyleSheet.absoluteFill}
        testID="branded-launch-video"
      />
    </View>
  );
}

export function BrandedLaunchSplash({ ready }: { ready: boolean }) {
  const [show, setShow] = useState(!completedInThisProcess);
  const completed = useRef(false);
  const finish = useCallback(() => {
    if (completed.current) return;
    completed.current = true;
    completedInThisProcess = true;
    setShow(false);
    hideNativeSplash();
  }, []);

  useEffect(() => {
    if (!show) hideNativeSplash();
  }, [show]);

  if (!show || !ready) return null;
  return (
    <BrandedSplashVideo onComplete={finish} onFirstFrame={hideNativeSplash} />
  );
}

const styles = StyleSheet.create({
  overlay: {
    ...StyleSheet.absoluteFill,
    backgroundColor: darkColors.background,
    zIndex: 1,
  },
});
