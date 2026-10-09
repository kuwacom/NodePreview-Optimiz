# 変更履歴

このプロジェクトの主な変更点を記録します。
書式は [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) を参考にしています。

このフォークの変更点は、README の「追加・改善機能」に載せています。

---

## 元プロジェクトの変更履歴

ここから下は、元プロジェクトの変更履歴をそのまま残したものです（原文は英語）。

### Node Preview Reborn（Guillaume Henrion aka GYOMH）

#### v1.0.1

- Fixed the automatic detection/removal of the original "Node Preview" addon (to avoid identifier
  conflicts when both are installed): the check now runs before this fork's own classes register
  and after Blender's startup context is fully ready, instead of racing with it. Previously this
  could either fail to disable the old addon cleanly, or fail outright at Blender startup if both
  addons were already enabled.
- Fixed a misleading console message that reported the old addon removal as failed even when it
  actually succeeded (caused by a harmless trailing error inside Blender's own addon_remove
  operator when called outside a normal UI context); the real outcome is now verified on disk

#### v1.0.0（upstream v1.22 ベース）

- Fixed a crash on recent Blender versions (5.0+): "context.scene.cycles.feature_set" no longer
  exists in Cycles, which silently broke every preview thumbnail
- Fixed a shader compilation error on the Vulkan GPU backend (Blender 5.0+) by migrating the
  thumbnail shader from the legacy GPUShader API to the modern, cross-backend GPUShaderCreateInfo API
- Added a "Vertical Offset" slider (0-50) to control the thumbnail's vertical offset from the node
  (previously hardcoded to a fixed value)
- "Thumbnail Scale" and the new "Vertical Offset" are now also available in the node editor's
  N-panel (sidebar > Node Preview tab), not just in the addon preferences

### Node Preview（Simon Wendsche）

#### v1.22

- Fix console spam on some OS by using TRIS instead of TRIANGLE_FAN batch for creating the thumbnail quads
- Automatically use sphere preview object on material (BSDF) shader nodes

#### v1.21

- Fixed a very rare race condition causing Blender to freeze when disabling the addon or closing Blender

#### v1.20

- Fixed text rendering being broken in Blender versions older that 4.0
- Fixed previews no longer updating after saving the .blend file under a new name in Blender 4.2

#### v1.19

- Fixed previews not working in Blender 4.1.1 when the node tree contained a linked image

#### v1.18

- Added an option in the user preferences to disable preview updates during animation playback
- Fixed image textures not loading when their name contains more than 57 characters
- Fixed previews not working in Blender 4.2 alpha

#### v1.17

- Hotfix for an issue with node groups. The Blender API for creating node group sockets was changed and now only
  allows 4 types of sockets to be created (vector, shader, float, color). All other socket types were leading to errors.

#### v1.16

- Added support for Float and Vector curve nodes
- Improved performance for node groups with lots of links between their nodes
- Improved image texture loading performance in the background process (e.g. from 3s to 0.6s loading time for a giant 40 megapixel image)
- Improved render result loading performance in the background process
- Added support for Raw and Non-Color colorspaces of image textures
- Fixed addon not working if another addon registers a buggy class
- Removed the "nodepreview_worker" binary module (replaced with Blender API and numpy). This makes the addon
  more future-proof, because a new Python version in Blender will no longer require a re-compilation of the binary module.
  The best thing however is that you no longer need to follow special steps when updating or removing the addon.
- Fixed a text rendering problem in Blender 4.0 beta caused by a change in the Blender API
- Fixed problems with node groups in Blender 4.0 beta caused by changes in the Blender API

#### v1.15

- Added support for UDIM images
- Added a new sphere preview mode. The default shortcut to switch between plane and sphere modes is Ctrl+P
- Eevee is now used to render the previews if Eevee is the active render engine.
  This means that Eevee-only nodes like "Shader to RGB" or "Specular BSDF" are now supported.
- Added a popover menu for Node Preview in the node editor header (button on the right)
- The addon now uses the new GPU module instead of the deprecated BGL module. This makes it more future-proof
  (as BGL will be removed at some point) and also solves a problem that happened on macOS with the new Metal backend.
- Fixed addon not loading in Blender 3.6 alpha due to a change in the Blender API (script_directories)

#### v1.14

- Fixed a bug causing previews to disappear ("error setting NodePreviewTreeProps.update_first_part")
  (this was a regression introduced in v1.11)

#### v1.13

- Fixed a minor bug where an operator poll function would raise an Exception instead of simply returning False
- Fixed background process sometimes not starting on macOS

#### v1.12

- Fixed errors happening when nodes had attributes registered by other addons
  (this was a regression introduced in v1.11)
- Fixed previews not updating occasionally when more than one node tree is opened
  (this was a regression introduced in v1.11)
- Fixed incorrect output socket being used on node group instances that have multiple outputs with the same name

#### v1.11

- Prevented potential problems when a node name inside a node group isn't a valid Python identifier (e.g. because it starts with a number)
- Improved performance in certain complex node trees. In one particular testscene, previews were only slowly
  showing up after 5 minutes of waiting - now they start appearing instantly and all previews for the tree are
  completed in a few seconds

#### v1.10

- Prevented problems when a material and a world have the same name and contain nodes with the same name
- Fixed preview thumbnails flickering in Blender 3.1 in the time between detaching a node wire and letting go of it
  (the node socket reports that it is still linked, while not actually being linked anymore, which might be a bug in Blender)
- Added support for OSL script nodes
- Fixed potential name collision problems when linking an image that has the same name as an existing image
  (e.g. there's a "stone.png" image in the .blend, and a different "stone.png" is linked in from another .blend)
- Fixed bug triggered by unconnected reroute nodes in node groups
- Added a workaround for a Blender bug (T97027/T97259) that made a diagonal line appear in the thumbnails in some cases

#### v1.9

- Added support for Python 3.10 on macOS (including on M1 CPUs)
- Added a shortcut for choosing the active output of a node manually. Before, the addon always used the first
  connected output automatically. This is still the default behaviour, but now the user can also select a node,
  press Shift+O, and choose any other output to be shown in the preview thumbnail.

#### v1.8

- Added support for Python 3.10 on Windows and Linux

#### v1.7

- Added support for the Apple Silicon (M1) version of Blender

#### v1.6

- Fixed previews not working after opening a .blend file directly (by double-clicking it in the OS file explorer)
  (this was a regression introduced in v1.5)
- Fixed some shader node previews not working in Blender 3.0

#### v1.5

- Fixed background process stopping when an image file did not exist at the specified path
- New packed images are now automatically loaded as soon as possible (when the .blend file is saved)
- Improved the error messages shown when an image file doesn't exist or could not be linked
- Fixed images not being reloaded if the path of an existing image datablock was modified
- If a packed file can't be linked, but exists on disk, it is now loaded from disk as fallback
- The debug log output can now be enabled in the user preferences (can be useful when making a bug report)
- Fixed old rendering jobs still being processed after loading a new .blend file (was a problem when opening
  a file with hundreds of nodes, then switching to another file before all thumbnails were rendered. Outdated jobs are now discarded)

#### v1.4

- Added support for Blender 2.93
- Fixed fallback for unsupported image formats not working and returning a black image
- Fixed addon not working if an alternative scripts path was set, but the addon was installed in the default location

#### v1.3

- Improved performance in complex node trees. In a scene with 295 nodes, the update checks took
  around 200 milliseconds before, which resulted in 5 frames per second in the node editor.
  Now, they only take around 40 milliseconds (25 frames per second)
- Fix UV Map output being black when using a UV map that doesn't exist on the preview mesh
- New shortcut: Ctrl+Shift+P toggles the node preview thumbnail of selected nodes on/off
- It is now possible to choose in the user preferences wether previews should be visible by default.
  You can set this to disabled if you only want a few nodes to show previews (use Ctrl+Shift+P to enable them)
- New controls in the N-Panel of the node editor (right side), with options to disable/enable
  previews for the whole node tree or selected nodes.

#### v1.2

- Added support for macOS
- Fixed frames in node groups causing all thumbnails for the current node tree to disappear
- Fixed unsupported nodes causing all previews to disappear
- Added support for custom nodes which are internally node groups, e.g. FxNodes

#### v1.1

- Enabled previews on the Geometry node
- Fixed addon not working if installed in an alternative scripts path (Preferences > File Paths > Data > Scripts)
- Users can now pick custom colors for the background which is shown behind transparent shaders
