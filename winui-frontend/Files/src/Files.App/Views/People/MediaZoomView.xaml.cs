// Copyright (c) Files Community
// Licensed under the MIT License.

using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Windows.Media.Playback;

namespace Files.App.Views.People
{
	// A picture or a playing video that zooms (pinch, Ctrl+scroll, double-click; the badge top-left
	// fits it again) with its own video controls (play, time, seek, mute) that stay put while zoomed.
	// Used by Who's who's review preview and by its full-size viewer, so both behave the same.
	// The owner creates the MediaPlayer and hands it over with SetPlayer; this control never owns it.
	public sealed partial class MediaZoomView : UserControl
	{
		public static readonly DependencyProperty ImageSourceProperty =
			DependencyProperty.Register(nameof(ImageSource), typeof(ImageSource), typeof(MediaZoomView), new(null));

		public static readonly DependencyProperty ImageVisibilityProperty =
			DependencyProperty.Register(nameof(ImageVisibility), typeof(Visibility), typeof(MediaZoomView), new(Visibility.Visible));

		public static readonly DependencyProperty PlayerVisibilityProperty =
			DependencyProperty.Register(nameof(PlayerVisibility), typeof(Visibility), typeof(MediaZoomView), new(Visibility.Collapsed));

		public static readonly DependencyProperty ImageNameProperty =
			DependencyProperty.Register(nameof(ImageName), typeof(string), typeof(MediaZoomView), new(string.Empty));

		public ImageSource? ImageSource
		{
			get => (ImageSource?)GetValue(ImageSourceProperty);
			set => SetValue(ImageSourceProperty, value);
		}

		public Visibility ImageVisibility
		{
			get => (Visibility)GetValue(ImageVisibilityProperty);
			set => SetValue(ImageVisibilityProperty, value);
		}

		public Visibility PlayerVisibility
		{
			get => (Visibility)GetValue(PlayerVisibilityProperty);
			set => SetValue(PlayerVisibilityProperty, value);
		}

		public string ImageName
		{
			get => (string)GetValue(ImageNameProperty);
			set => SetValue(ImageNameProperty, value);
		}

		public MediaZoomView()
		{
			InitializeComponent();
		}

		// --- Zoom -------------------------------------------------------------------

		private const float DoubleTapZoom = 2.5f;

		private void ZoomScroller_SizeChanged(object sender, SizeChangedEventArgs e)
		{
			ZoomContent.Width = e.NewSize.Width;
			ZoomContent.Height = e.NewSize.Height;
		}

		private void ZoomScroller_ViewChanged(object? sender, ScrollViewerViewChangedEventArgs e)
		{
			var zoom = ZoomScroller.ZoomFactor;
			ZoomResetButton.Visibility = zoom > 1.01f ? Visibility.Visible : Visibility.Collapsed;
			ZoomText.Text = $"{Math.Round(zoom * 100)}%";
		}

		private void ZoomScroller_DoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
		{
			if (ZoomScroller.ZoomFactor > 1.01f)
			{
				ResetZoom(false);
				return;
			}
			// Zoom in around the point that was double-clicked (at 100% content and viewport coincide).
			var p = e.GetPosition(ZoomContent);
			ZoomScroller.ChangeView(p.X * (DoubleTapZoom - 1), p.Y * (DoubleTapZoom - 1), DoubleTapZoom);
		}

		private void ZoomReset_Click(object sender, RoutedEventArgs e)
			=> ResetZoom(false);

		public void ResetZoom(bool instantly)
			=> ZoomScroller.ChangeView(0, 0, 1, instantly);

		// --- Video --------------------------------------------------------------------

		public MediaPlayer? Player => PlayerElement.MediaPlayer;

		private bool movingSeekFromPlayer;

		// Shows `player` (or nothing) and drives the controls from it.
		public void SetPlayer(MediaPlayer? player)
		{
			PlayerElement.SetMediaPlayer(player);
			if (player is null)
				return;
			UpdateVideoBar();
			void Update(MediaPlaybackSession s, object _) => DispatcherQueue.TryEnqueue(() => { if (Player == player) UpdateVideoBar(); });
			player.PlaybackSession.PositionChanged += Update;
			player.PlaybackSession.NaturalDurationChanged += Update;
			player.PlaybackSession.PlaybackStateChanged += Update;
		}

		private void UpdateVideoBar()
		{
			if (Player is not { } player)
				return;
			var session = player.PlaybackSession;
			movingSeekFromPlayer = true;
			VideoSeek.Maximum = Math.Max(session.NaturalDuration.TotalSeconds, 0.1);
			VideoSeek.Value = Math.Min(session.Position.TotalSeconds, VideoSeek.Maximum);
			movingSeekFromPlayer = false;
			VideoTimeText.Text = $"{Clock(session.Position)} / {Clock(session.NaturalDuration)}";

			var playing = session.PlaybackState is MediaPlaybackState.Playing or MediaPlaybackState.Opening or MediaPlaybackState.Buffering;
			VideoPlayIcon.Glyph = playing ? "" : "";
			Label(VideoPlayButton, playing ? Strings.MediaMind_ReviewVideoPause : Strings.MediaMind_ReviewVideoPlay);
			VideoMuteIcon.Glyph = player.IsMuted ? "" : "";
			Label(VideoMuteButton, player.IsMuted ? Strings.MediaMind_ReviewVideoUnmute : Strings.MediaMind_ReviewVideoMute);
		}

		private const int VideoBarHideDelayMs = 500;
		private Microsoft.UI.Dispatching.DispatcherQueueTimer? videoBarHideTimer;

		private void Root_PointerEntered(object sender, PointerRoutedEventArgs e)
		{
			videoBarHideTimer?.Stop();
			SetVideoBarShown(true);
		}

		private void Root_PointerExited(object sender, PointerRoutedEventArgs e)
		{
			if (videoBarHideTimer is null)
			{
				videoBarHideTimer = DispatcherQueue.CreateTimer();
				videoBarHideTimer.Interval = TimeSpan.FromMilliseconds(VideoBarHideDelayMs);
				videoBarHideTimer.IsRepeating = false;
				videoBarHideTimer.Tick += (_, _) => SetVideoBarShown(false);
			}
			videoBarHideTimer.Start();
		}

		private void SetVideoBarShown(bool shown)
		{
			VideoBar.Opacity = shown ? 1 : 0;
			VideoBar.IsHitTestVisible = shown;
		}

		private static string Clock(TimeSpan t)
			=> t.ToString(t.TotalHours >= 1 ? @"h\:mm\:ss" : @"m\:ss");

		private static void Label(FrameworkElement element, string resource)
		{
			var text = resource.GetLocalizedResource();
			AutomationProperties.SetName(element, text);
			ToolTipService.SetToolTip(element, text);
		}

		private void VideoPlay_Click(object sender, RoutedEventArgs e)
		{
			if (Player is not { } player)
				return;
			if (player.PlaybackSession.PlaybackState is MediaPlaybackState.Playing)
				player.Pause();
			else
				player.Play();
			UpdateVideoBar();
		}

		private void VideoMute_Click(object sender, RoutedEventArgs e)
		{
			if (Player is not { } player)
				return;
			player.IsMuted = !player.IsMuted;
			UpdateVideoBar();
		}

		private void VideoSeek_ValueChanged(object sender, RangeBaseValueChangedEventArgs e)
		{
			if (!movingSeekFromPlayer && Player is { } player)
				player.PlaybackSession.Position = TimeSpan.FromSeconds(e.NewValue);
		}
	}
}
