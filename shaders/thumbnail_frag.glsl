/*
    This file is part of Node Preview Reborn, a fork of NodePreview.
    Copyright (C) 2021 Simon Wendsche
    Copyright (C) 2026 Guillaume Henrion aka GYOMH (fork/modifications)

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
*/

void main() {
    vec4 imageColor = texture(image, texCoord_interp);

    if (gamma_correct) {
        const float gamma = 2.2f;
        imageColor.rgb = pow(imageColor.rgb, vec3(gamma));
    }

    // Slanted corners
    const float dist = 0.98f;
    vec2 point = abs(texCoord_interp * 2.f - 1.f);
    float opacity = float(point.x + point.y < dist + dist);
    imageColor.a = min(imageColor.a, opacity);

    fragColor = imageColor;
}
