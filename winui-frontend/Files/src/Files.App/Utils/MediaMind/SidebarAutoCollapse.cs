// Copyright (c) Files Community
// Licensed under the MIT License.

using Files.App.Controls;
using Files.App.ViewModels.UserControls;

namespace Files.App.Utils.MediaMind
{
	// MediaMind: work-heavy pages (Who's who, review) start with the navigation sidebar
	// collapsed to its icon strip (the ☰ button reopens it) and put it back on leave.
	internal static class SidebarAutoCollapse
	{
		private static bool collapsedByUs;

		public static void Enter()
		{
			var sidebar = Ioc.Default.GetRequiredService<SidebarViewModel>();
			if (sidebar.SidebarDisplayMode != SidebarDisplayMode.Expanded)
				return;
			sidebar.SidebarDisplayMode = SidebarDisplayMode.Compact;
			collapsedByUs = true;
		}

		public static void Leave()
		{
			if (!collapsedByUs)
				return;
			collapsedByUs = false;
			var sidebar = Ioc.Default.GetRequiredService<SidebarViewModel>();
			// Only restore if the user didn't reopen it themselves meanwhile.
			if (sidebar.SidebarDisplayMode == SidebarDisplayMode.Compact)
				sidebar.SidebarDisplayMode = SidebarDisplayMode.Expanded;
		}
	}
}
