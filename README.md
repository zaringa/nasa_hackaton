# NASA Space Apps Challenge 2026 — Lunar Light and Earth Visibility

The mathematical foundation of an application for comparing lunar landing sites and mission dates. The model combines spacecraft coordinates and height, a terrain horizon, and time-dependent Sun and Earth vectors to calculate direct sunlight and geometric Earth visibility.

The derivations cover input coordinates, the local basis, terrain visibility, the solar disc, panel power, and time windows. Each derivation appears alongside the calculation that uses it. The current repository implements the formula functions and a sampled calculation path; terrain data ingestion, kernel preparation, caching, and application output metadata are integration work. Section 17 states the exact inputs and outputs of the current code.

**Core idea:** for a stationary spacecraft, compute the terrain horizon profile once. Then compare the Sun and Earth positions with that profile at each time. Reuse the same horizon when changing the mission date.

## Contents

1. [Problem and use cases](#challenge)
2. [Inputs, outputs, and assumptions](#model)
3. [Data sources and coordinate consistency](#data)
4. [Surface and observer positions](#position)
5. [Deriving the local east, north, and up basis](#basis)
6. [Transforming global coordinates into local coordinates](#transform)
7. [Azimuth and elevation](#angles)
8. [Terrain horizon and lunar curvature](#horizon)
9. [Terrain coverage and resolution](#terrain)
10. [Sun and Earth positions with SPICE](#ephemeris)
11. [The solar disc and its visible fraction](#solar-disc)
12. [Solar occultation by Earth](#eclipse)
13. [Earth visibility and communications](#earth)
14. [From solar visibility to panel power](#power)
15. [Finding rises, sets, and window boundaries](#events)
16. [Durations, energy, and joint windows](#metrics)
17. [Computational core structure](#architecture)
18. [Model validation and accuracy](#validation)
19. [Presenting results in the application](#visualization)
20. [References and further reading](#references)
21. [Coverage of the original material](#source-coverage)

<a id="challenge"></a>

## 1. Problem and use cases

The NASA Space Apps Challenge problem is to make lunar landing site assessment understandable and fast. A planner needs to compare combinations of location and date, examine solar energy availability and direct Earth visibility, and quickly assess alternatives when a mission is rescheduled.

Local terrain is particularly important near the south pole. The Sun can travel low above the horizon, and a crater rim can block it even when its elevation above the horizontal plane is positive. Changing the spacecraft position or panel height changes the surrounding horizon and the available sunlight intervals.

The application should answer specific questions:

- Which site receives more direct sunlight during the selected period?
- How much time remains before sunlight disappears or the direction toward Earth becomes blocked?
- What is the longest continuous interruption in illumination or Earth visibility?
- What changes if the landing is moved to another date?
- When are the illumination and geometric Earth visibility criteria satisfied simultaneously?

Sites can be selected from a catalogue of known landing locations or entered as custom coordinates. Comparisons use the same metric definitions and model settings, with comparable analysis durations when different dates are evaluated.

<a id="model"></a>

## 2. Inputs, outputs, and assumptions

### Application inputs

| Parameter | Meaning |
| --- | --- |
| Latitude and longitude | Landing site position in the selected lunar reference frame |
| Observer height | Panel or antenna height above the ground at the landing site |
| Start and end times | Analysis interval entered in UTC |
| Digital elevation model, DEM | Surface elevations and the coordinate reference system description |
| Sufficient illumination criterion | For example, a minimum visible solar disc fraction |
| Accuracy settings | Spatial sampling, time step, and refinement tolerances |
| Optional panel parameters | Area, orientation, and conversion efficiency for power estimation |

### Mathematical outputs

At each time, calculate the azimuth and elevation of the Sun and Earth, their angular clearance above terrain, the visible solar disc fraction, and an Earth visibility state. Extract continuous windows from the time series and calculate metrics for comparing scenarios. The combined `analyze` function currently uses the Earth-centre visibility criterion. The alternative disc and station criteria in section 13 describe separate calculations or later integration.

### Basic assumptions

In the minimum version, the spacecraft is stationary relative to the Moon, and the surface is represented by a **reference sphere plus radial terrain elevation**. The nonnegative spacecraft height is also measured radially, outward from the local ground in the direction away from the lunar centre.

The panel and antenna can initially share one calculation point. If their heights differ, each point requires its own horizon profile.

The model considers direct rays without atmospheric refraction. The solar and terrestrial discs have spherical geometry in the basic model; the solar disc brightness is assumed uniform when calculating its visible fraction. Reflected light and thermal conditions require additional models.

**Accounting for all terrain means accounting for all influential terrain represented in the selected DEM.** Rocks, narrow ridges, and other features absent from the source data cannot be recovered by this model.

### Main notation

| Symbol | Meaning |
| --- | --- |
| $R$ | Reference sphere radius used by the DEM |
| $\varphi,\lambda$ | Planetocentric latitude and east longitude |
| $\varphi_0,\lambda_0$ | Site coordinates |
| $z(\varphi,\lambda)$ | Radial ground elevation from the DEM |
| $z_0$ | Ground elevation at the landing site |
| $h$ | Radial observer height above the ground |
| $r_o,\mathbf p$ | Observer distance from the lunar centre and position vector |
| $\mathbf q$ | Position vector of a terrain point |
| $\mathbf e,\mathbf n,\mathbf u$ | Unit vectors toward east, north, and up |
| $A,\varepsilon$ | Celestial object azimuth and elevation |
| $\beta,H(A)$ | Terrain point elevation angle and horizon profile |
| $\rho_B$ | Angular radius of body $B$ |
| $f_S(t)$ | Visible solar disc fraction after the selected obstructions are applied |
| $I_S(t),I_E(t)$ | Indicators of the illumination and Earth visibility criteria |
| $P(t),W$ | Panel electrical power and generated energy |

Formulas use metres and radians; angles are converted into degrees for display. Distances are converted into kilometres at the SPICE interface. Numerical calculations use `float64`.

<a id="data"></a>

## 3. Data sources and coordinate consistency

SPICE, accessed through the Python library SpiceyPy, provides celestial body positions and lunar orientation. Surface geometry comes from digital elevation models produced using LOLA, the laser altimeter aboard LRO.

NASA publishes [detailed DEMs of selected south polar sites on a 5 m/pixel grid](https://pgda.gsfc.nasa.gov/products/78) and [models covering a wider region](https://pgda.gsfc.nasa.gov/products/90). Grid spacing is distinct from actual resolving power and elevation uncertainty: a small pixel does not by itself guarantee that every feature of that size has been measured.

The [polar LOLA products considered here](https://pgda.gsfc.nasa.gov/products/69) use the reference radius:

<a id="eq-001"></a>

$$
R=1\,737\,400\ \text{m}.
$$

An implementation must read this value from the selected dataset description, together with its units, elevation scaling, map projection, and missing data conventions.

**The site coordinates, DEM, observer position, and celestial directions must use a consistent lunar frame.** Merely describing all coordinates as lunar latitude and longitude is insufficient.

For example, [NASA's regional DEMs](https://pgda.gsfc.nasa.gov/products/90) are described in the DE421 realization of `MOON_ME`. SPICE calculations must explicitly select the matching realization and supporting kernels. `MOON_ME` can be an alias determined by the loaded frame kernel, so preserve the exact realization name and kernel set. The [official NAIF lunar frame kernel](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_de440_250416.tf) illustrates these definitions.

The installed requirement for the current formula implementation is NumPy. The optional SPICE wrapper requires SpiceyPy; the remaining tools below are options for integrating actual terrain data or other numerical methods.

| Tool | Role in the computational core |
| --- | --- |
| SpiceyPy | Sun and Earth ephemerides, lunar orientation, and time conversion |
| NumPy | Vectors, matrices, projections, and time series arrays |
| Rasterio | Raster DEMs, georeferencing, and missing data masks |
| pyproj | Explicitly defined lunar map projections |
| SciPy | Numerical refinement of event boundaries for suitable functions |

<a id="position"></a>

## 4. Surface and observer positions

### 4.1. Defining global coordinates

Choose a frame rotating with the Moon:

- its origin is at the lunar centre;
- the $Z$ axis points toward the north pole of the selected frame;
- the $X$ axis passes through the equator and prime meridian;
- the $Y$ axis passes through the equator at $90^\circ$ east longitude.

Latitude $\varphi$ is **planetocentric**: the angle between the outward radial direction and the equatorial plane. Longitude $\lambda$ increases from $X$ toward $Y$. These definitions match the [SPICE `latrec` transformation](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/latrec_c.html).

Convert degrees into radians using:

<a id="eq-002"></a>

$$
\theta_{\mathrm{rad}}=\theta_{\mathrm{deg}}\frac{\pi}{180}.
$$

### 4.2. Deriving the position vector

Let the distance from the lunar centre to a point be $r$. The radius makes an angle $\varphi$ with the equatorial plane, so its vertical component is:

<a id="eq-003"></a>

$$
Z=r\sin\varphi.
$$

The length of its projection onto the equatorial plane is:

<a id="eq-004"></a>

$$
L_{XY}=r\cos\varphi.
$$

This projection makes an angle $\lambda$ with the $X$ axis. Resolve it along the two axes:

<a id="eq-005"></a>

$$
X=L_{XY}\cos\lambda,
\qquad
Y=L_{XY}\sin\lambda.
$$

Substitution gives:

<a id="eq-006"></a>

$$
\boxed{
\mathbf r(r,\varphi,\lambda)=
\begin{pmatrix}
r\cos\varphi\cos\lambda\\
r\cos\varphi\sin\lambda\\
r\sin\varphi
\end{pmatrix}.
}
$$

The factor $r$ sets the scale, $\cos\varphi$ selects the part in the equatorial plane, and $\cos\lambda$ and $\sin\lambda$ distribute that projection between $X$ and $Y$.

Check three simple cases:

<a id="eq-007"></a>

$$
\begin{aligned}
\varphi=0,\ \lambda=0
&\quad\Rightarrow\quad \mathbf r=(r,0,0)^{\mathsf T},\\
\varphi=0,\ \lambda=90^\circ
&\quad\Rightarrow\quad \mathbf r=(0,r,0)^{\mathsf T},\\
\varphi=90^\circ
&\quad\Rightarrow\quad \mathbf r=(0,0,r)^{\mathsf T}.
\end{aligned}
$$

These are points on the positive $X$, $Y$, and $Z$ axes, respectively.

### 4.3. Observer and terrain positions

Divide the position vector by its length to obtain the radial unit vector:

<a id="eq-008"></a>

$$
\mathbf u(\varphi,\lambda)=\frac{\mathbf r}{r}=
\begin{pmatrix}
\cos\varphi\cos\lambda\\
\cos\varphi\sin\lambda\\
\sin\varphi
\end{pmatrix}.
$$

First read the ground elevation at the site:

<a id="eq-009"></a>

$$
z_0=z(\varphi_0,\lambda_0).
$$

The observer distance from the centre and its position are:

<a id="eq-010"></a>

$$
r_o=R+z_0+h,
\qquad
\boxed{\mathbf p=r_o\mathbf u(\varphi_0,\lambda_0).}
$$

Ground elevation and spacecraft height add together. For example:

<a id="eq-011"></a>

$$
R=1\,737\,400\ \text{m},\quad
z_0=1000\ \text{m},\quad h=2\ \text{m}
\quad\Rightarrow\quad
r_o=1\,738\,402\ \text{m}.
$$

Any terrain point has the position:

<a id="eq-012"></a>

$$
\boxed{
\mathbf q=(R+z(\varphi,\lambda))\mathbf u(\varphi,\lambda).
}
$$

If height must later be measured along a tilted mast, define the observer position using a vector offset from the ground. This is a different height convention and must be specified explicitly.

<a id="basis"></a>

## 5. Deriving the local east, north, and up basis

Global $X,Y,Z$ coordinates are convenient for positions, but an observer needs local directions. Define unit vectors $\mathbf e$ toward east, $\mathbf n$ toward north, and $\mathbf u$ upward. Together they form the ENU basis: East, North, Up.

The following derivations use arbitrary $\varphi,\lambda$. Substitute $\varphi_0,\lambda_0$ for the spacecraft location.

### 5.1. Up by increasing distance from the centre

In this model, moving upward keeps latitude and longitude constant while increasing $r$. The direction is therefore given by the derivative:

<a id="eq-013"></a>

$$
\boxed{
\mathbf u=\frac{\partial\mathbf r}{\partial r}=
\begin{pmatrix}
\cos\varphi\cos\lambda\\
\cos\varphi\sin\lambda\\
\sin\varphi
\end{pmatrix}.
}
$$

This is the same unit vector obtained by dividing $\mathbf r$ by $r$.

For example, at $\varphi=30^\circ,\lambda=0^\circ$:

<a id="eq-014"></a>

$$
\mathbf u=(\sqrt3/2,\ 0,\ 1/2)^{\mathsf T}.
$$

Local up points in both the positive $X$ and positive $Z$ directions. It coincides with the positive global $Z$ direction only at the north pole.

### 5.2. East by increasing longitude

Moving east follows a parallel: $\lambda$ increases while $r$ and $\varphi$ remain fixed. For a small longitude increment:

<a id="eq-015"></a>

$$
\mathbf r(r,\varphi,\lambda+\Delta\lambda)-\mathbf r(r,\varphi,\lambda)
\approx
\frac{\partial\mathbf r}{\partial\lambda}\Delta\lambda.
$$

The derivative gives the tangent direction of this motion. The component derivatives use the ordinary trigonometric rules:

<a id="eq-016"></a>

$$
\frac{d}{d\lambda}\cos\lambda=-\sin\lambda,\qquad\frac{d}{d\lambda}\sin\lambda=\cos\lambda.
$$

Differentiate the three components:

<a id="eq-017"></a>

$$
\frac{\partial\mathbf r}{\partial\lambda}=
\begin{pmatrix}
-r\cos\varphi\sin\lambda\\
r\cos\varphi\cos\lambda\\
0
\end{pmatrix}
=r\cos\varphi
\begin{pmatrix}
-\sin\lambda\\
\cos\lambda\\
0
\end{pmatrix}.
$$

The minus sign in the first component comes from $(\cos\lambda)'=-\sin\lambda$. The third component is zero because $Z=r\sin\varphi$ does not change along a parallel.

Away from the poles, $\cos\varphi>0$. The length of the derivative is:

<a id="eq-018"></a>

$$
\left\|\frac{\partial\mathbf r}{\partial\lambda}\right\|=r\cos\varphi\sqrt{\sin^2\lambda+\cos^2\lambda}=r\cos\varphi.
$$

Normalize the derivative by dividing by this length:

<a id="eq-019"></a>

$$
\boxed{
\mathbf e=
\frac{\partial\mathbf r/\partial\lambda}
{\|\partial\mathbf r/\partial\lambda\|}
=
\begin{pmatrix}
-\sin\lambda\\
\cos\lambda\\
0
\end{pmatrix}.
}
$$

Latitude affects the size of the parallel and the distance travelled, but normalization leaves only the tangent direction.

At $\lambda=0^\circ$, east points along $+Y$; at $\lambda=90^\circ$, it points along $-X$.

<a id="eq-020"></a>

$$
\begin{aligned}
\lambda=0^\circ&\quad\Rightarrow\quad\mathbf e=(0,1,0)^{\mathsf T},\\
\lambda=90^\circ&\quad\Rightarrow\quad\mathbf e=(-1,0,0)^{\mathsf T}.
\end{aligned}
$$

### 5.3. North by increasing latitude

Moving north follows a meridian: $\varphi$ increases while $r$ and $\lambda$ remain fixed. The derivative is:

<a id="eq-021"></a>

$$
\frac{\partial\mathbf r}{\partial\varphi}=
\begin{pmatrix}
-r\sin\varphi\cos\lambda\\
-r\sin\varphi\sin\lambda\\
r\cos\varphi
\end{pmatrix}.
$$

Factor out the radius:

<a id="eq-022"></a>

$$
\frac{\partial\mathbf r}{\partial\varphi}=r
\begin{pmatrix}
-\sin\varphi\cos\lambda\\
-\sin\varphi\sin\lambda\\
\cos\varphi
\end{pmatrix}.
$$

Its length is:

<a id="eq-023"></a>

$$
\left\|\frac{\partial\mathbf r}{\partial\varphi}\right\|
=r\sqrt{\sin^2\varphi(\cos^2\lambda+\sin^2\lambda)+\cos^2\varphi}=r.
$$

Divide by $r$ to obtain the unit north direction:

<a id="eq-024"></a>

$$
\boxed{
\mathbf n=
\begin{pmatrix}
-\sin\varphi\cos\lambda\\
-\sin\varphi\sin\lambda\\
\cos\varphi
\end{pmatrix}.
}
$$

At $\varphi=30^\circ,\lambda=0^\circ$:

<a id="eq-025"></a>

$$
\mathbf n=(-1/2,\ 0,\ \sqrt3/2)^{\mathsf T}.
$$

Moving north increases $Z$ while decreasing the distance to the $Z$ axis. This explains the negative first component in this example.

### 5.4. Checking length, orthogonality, and orientation

A coordinate basis needs unit lengths and mutually perpendicular vectors:

<a id="eq-026"></a>

$$
\begin{aligned}
\|\mathbf e\|=\|\mathbf n\|=\|\mathbf u\|&=1,\\
\mathbf e\cdot\mathbf n=\mathbf e\cdot\mathbf u=\mathbf n\cdot\mathbf u&=0.
\end{aligned}
$$

Check these properties using $\sin^2x+\cos^2x=1$:

<a id="eq-027"></a>

$$
\|\mathbf e\|^2=\sin^2\lambda+\cos^2\lambda=1,
$$

<a id="eq-028"></a>

$$
\begin{aligned}
\|\mathbf n\|^2
&=\sin^2\varphi\cos^2\lambda+\sin^2\varphi\sin^2\lambda+\cos^2\varphi\\
&=\sin^2\varphi(\cos^2\lambda+\sin^2\lambda)+\cos^2\varphi\\
&=1.
\end{aligned}
$$

<a id="eq-029"></a>

$$
\|\mathbf u\|^2=
\cos^2\varphi(\cos^2\lambda+\sin^2\lambda)+\sin^2\varphi=1.
$$

The dot product of east and north is:

<a id="eq-030"></a>

$$
\mathbf e\cdot\mathbf n=
\sin\lambda\sin\varphi\cos\lambda
-\cos\lambda\sin\varphi\sin\lambda=0.
$$

For north and up:

<a id="eq-031"></a>

$$
\mathbf n\cdot\mathbf u=
-\sin\varphi\cos\varphi(\cos^2\lambda+\sin^2\lambda)
+\sin\varphi\cos\varphi=0.
$$

The remaining dot product is:

<a id="eq-032"></a>

$$
\mathbf e\cdot\mathbf u
=(-\sin\lambda)(\cos\varphi\cos\lambda)
+(\cos\lambda)(\cos\varphi\sin\lambda)=0.
$$

Finally, the orientation is fixed by:

<a id="eq-033"></a>

$$
\boxed{\mathbf e\times\mathbf n=\mathbf u.}
$$

East, north, and up therefore form a **right-handed orthonormal basis**. The same directions and matrices appear in [ESA Navipedia, equations 4–6](https://gssc.esa.int/navipedia/index.php/Transformations_between_ECEF_and_ENU_coordinates). This lunar spherical model uses planetocentric latitude.

### 5.5. The pole and the surface slope

All meridians meet at an exact geographic pole. The longitude derivative becomes zero, so local east and north require a chosen reference meridian. The formulas then define an agreed orientation of the local axes.

Radial up, the surface normal, and the panel normal must also be distinguished. We differentiated a sphere at constant radius. For actual terrain $\mathbf q=r(\varphi,\lambda)\mathbf u$, the derivative contains an additional term:

<a id="eq-034"></a>

$$
\frac{\partial\mathbf q}{\partial\varphi}
=\frac{\partial r}{\partial\varphi}\mathbf u+r\mathbf n.
$$

This term represents the change in surface elevation. The ENU basis therefore does not automatically determine the orientation of a panel installed on sloping ground.

<a id="transform"></a>

## 6. Transforming global coordinates into local coordinates

### 6.1. Why dot products are needed

Let $\mathbf v$ be a vector in global lunar coordinates. Expand it along the local directions:

<a id="eq-035"></a>

$$
\mathbf v=E\mathbf e+N\mathbf n+U\mathbf u.
$$

The coefficients $E,N,U$ are the east, north, and up components. Take the dot product of both sides with $\mathbf e$:

<a id="eq-036"></a>

$$
\begin{aligned}
\mathbf v\cdot\mathbf e
&=E(\mathbf e\cdot\mathbf e)
+N(\mathbf n\cdot\mathbf e)
+U(\mathbf u\cdot\mathbf e)\\
&=E\cdot1+N\cdot0+U\cdot0=E.
\end{aligned}
$$

Unit lengths and orthogonality isolate the required component. Similarly:

<a id="eq-037"></a>

$$
\boxed{
E=\mathbf v\cdot\mathbf e,\qquad
N=\mathbf v\cdot\mathbf n,\qquad
U=\mathbf v\cdot\mathbf u.
}
$$

### 6.2. Matrix rows and columns

Place the basis vectors in the columns of a matrix:

<a id="eq-038"></a>

$$
\mathbf B=
\begin{pmatrix}
\vert&\vert&\vert\\
\mathbf e&\mathbf n&\mathbf u\\
\vert&\vert&\vert
\end{pmatrix}.
$$

This matrix converts local components into global coordinates:

<a id="eq-039"></a>

$$
\boxed{\mathbf v=\mathbf B(E,N,U)^{\mathsf T}.}
$$

For the inverse transformation, place the basis vectors in rows: each row calculates one dot product.

<a id="eq-040"></a>

$$
\boxed{
\begin{pmatrix}E\\N\\U\end{pmatrix}
=
\underbrace{
\begin{pmatrix}
-\sin\lambda_0&\cos\lambda_0&0\\
-\sin\varphi_0\cos\lambda_0&-\sin\varphi_0\sin\lambda_0&\cos\varphi_0\\
\cos\varphi_0\cos\lambda_0&\cos\varphi_0\sin\lambda_0&\sin\varphi_0
\end{pmatrix}
}_{\mathbf B^{\mathsf T}}
\mathbf v.
}
$$

Orthonormality gives $\mathbf B^{\mathsf T}\mathbf B=\mathbf I$, so:

<a id="eq-041"></a>

$$
\boxed{\mathbf B^{-1}=\mathbf B^{\mathsf T}.}
$$

Transposition exchanges rows and columns. Confusing the transformation directions produces incorrect local coordinates even when the basis vectors themselves are correct.

### 6.3. The origin of the object vector

If $\mathbf r_B(t)$ is the geometric position of a body's centre relative to the lunar centre in the same frame, the vector from the spacecraft to the body is:

<a id="eq-042"></a>

$$
\boxed{\mathbf v_B(t)=\mathbf r_B(t)-\mathbf p.}
$$

For terrain, use $\mathbf v_T=\mathbf q-\mathbf p$ in the same way.

Subtraction is necessary because the direction from the lunar centre differs from the direction from the spacecraft. If a library already returns an observer-relative vector, do not subtract $\mathbf p$ again. For apparent positions with light-time corrections, obtain that vector directly from SPICE as described in [section 10](#ephemeris).

<a id="angles"></a>

## 7. Azimuth and elevation

### 7.1. Deriving elevation

The horizontal component of the local vector has length:

<a id="eq-043"></a>

$$
L=\sqrt{E^2+N^2}.
$$

In a right triangle with legs $L$ and $U$:

<a id="eq-044"></a>

$$
\tan\varepsilon=\frac UL.
$$

Use `atan2` to calculate the angle while preserving component signs and limiting directions:

<a id="eq-045"></a>

$$
\boxed{
\varepsilon=\operatorname{atan2}\left(U,\sqrt{E^2+N^2}\right).
}
$$

The same right triangle gives:

<a id="eq-046"></a>

$$
\sin\varepsilon=\frac{U}{\sqrt{E^2+N^2+U^2}}=\frac{U}{\|\mathbf v\|}.
$$

Taking the inverse sine produces the equivalent elevation expression:

<a id="eq-047"></a>

$$
\boxed{
\varepsilon=\arcsin\frac{U}{\|\mathbf v\|}.
}
$$

Positive $U$ means the object is above the local horizontal plane; negative $U$ means it is below. This plane is perpendicular to radial up. The terrain horizon can lie on either side of it.

### 7.2. Deriving azimuth

Measure azimuth from north toward east:

<a id="eq-048"></a>

$$
0^\circ=\text{north},\quad
90^\circ=\text{east},\quad
180^\circ=\text{south},\quad
270^\circ=\text{west}.
$$

The horizontal projection components are then:

<a id="eq-049"></a>

$$
N=L\cos A,\qquad E=L\sin A.
$$

Therefore:

<a id="eq-050"></a>

$$
\boxed{A=\operatorname{atan2}(E,N)\pmod{2\pi}.}
$$

**Argument order matters: east first, north second.** Ordinary $\arctan(E/N)$ loses the quadrant: $1/1$ and $(-1)/(-1)$ are equal ratios despite representing opposite directions.

When $E=N=0$, the object is at the zenith or nadir and azimuth is undefined. A zero vector defines no direction and must be handled separately.

### 7.3. A complete numerical example

Consider an illustrative site at $\varphi_0=30^\circ,\lambda_0=0^\circ$. Its basis is:

<a id="eq-051"></a>

$$
\mathbf e=
\begin{pmatrix}0\\1\\0\end{pmatrix},\quad
\mathbf n=
\begin{pmatrix}-1/2\\0\\\sqrt3/2\end{pmatrix},\quad
\mathbf u=
\begin{pmatrix}\sqrt3/2\\0\\1/2\end{pmatrix}.
$$

Let the observer-to-object vector, in arbitrary consistent units, be:

<a id="eq-052"></a>

$$
\mathbf v=
\begin{pmatrix}\sqrt3/2\\1\\5/2\end{pmatrix}.
$$

Projection gives:

<a id="eq-053"></a>

$$
\begin{aligned}
E&=1,\\
N&=-\frac12\frac{\sqrt3}{2}+\frac{\sqrt3}{2}\frac52
=-\frac{\sqrt3}{4}+\frac{5\sqrt3}{4}=\sqrt3,\\
U&=\frac{\sqrt3}{2}\frac{\sqrt3}{2}+\frac12\frac52
=\frac34+\frac54=2.
\end{aligned}
$$

Thus $L=\sqrt{1+3}=2$, and:

<a id="eq-054"></a>

$$
\boxed{\varepsilon=\operatorname{atan2}(2,2)=45^\circ,}
$$

<a id="eq-055"></a>

$$
\boxed{A=\operatorname{atan2}(1,\sqrt3)=30^\circ.}
$$

The object is $30^\circ$ east of north and $45^\circ$ above the horizontal plane. This example checks the geometry and does not represent a particular lunar date.

<a id="horizon"></a>

## 8. Terrain horizon and lunar curvature

### 8.1. What the horizon profile represents

The function $H(A)$ answers the question: **up to what elevation does the surface block the sky at azimuth $A$?**

For each terrain point, construct $\mathbf q-\mathbf p$, project it onto ENU, and calculate its azimuth and elevation angle $\beta$. The sky boundary is the highest angular elevation among terrain points in that direction:

<a id="eq-056"></a>

$$
\boxed{H(A)=\sup_{\text{terrain along }A}\beta.}
$$

The symbol $\sup$ denotes the least upper bound. When the highest value is attained, it is the ordinary maximum. This definition also handles limiting cases of a continuous surface.

If three ridges in one direction have elevation angles $1^\circ$, $3^\circ$, and $2^\circ$, then $H(A)=3^\circ$. A point source at $2.5^\circ$ is blocked, while one at $3.5^\circ$ is visible.

Define a celestial body's angular clearance above terrain:

<a id="eq-057"></a>

$$
\boxed{g_B(t)=\varepsilon_B(t)-H(A_B(t)).}
$$

The direction toward the body centre is open when $g_B>0$ and blocked when $g_B<0$. Equality represents contact with the boundary. Retaining $g_B$ itself shows how close a result is to a visibility transition.

### 8.2. Moving along a chosen azimuth

The horizontal unit direction at azimuth $A$ is:

<a id="eq-058"></a>

$$
\mathbf w(A)=\cos A\,\mathbf n+\sin A\,\mathbf e.
$$

Let $\psi$ be the central angle between the site and a terrain point. The radial direction toward that point can be written using two perpendicular unit vectors:

<a id="eq-059"></a>

$$
\boxed{
\mathbf u_{\psi,A}=\cos\psi\,\mathbf u+\sin\psi\,\mathbf w(A).
}
$$

This follows a great circle on the sphere. Recover latitude and longitude from the components of $\mathbf u_{\psi,A}$, read $z(\psi,A)$ from the DEM, and calculate the radius:

<a id="eq-060"></a>

$$
r(\psi,A)=R+z(\psi,A).
$$

### 8.3. Exact terrain elevation angle

The surface point position is:

<a id="eq-061"></a>

$$
\mathbf q=r(\psi,A)
\left[\cos\psi\,\mathbf u+\sin\psi\,\mathbf w(A)\right].
$$

Subtract $\mathbf p=r_o\mathbf u$:

<a id="eq-062"></a>

$$
\mathbf q-\mathbf p=
\underbrace{(r\cos\psi-r_o)\mathbf u}_{\text{vertical component}}
+\underbrace{r\sin\psi\,\mathbf w(A)}_{\text{horizontal component}}.
$$

Apply the previously derived angle formula:

<a id="eq-063"></a>

$$
\boxed{
\beta(\psi,A)=\operatorname{atan2}
\left(r(\psi,A)\cos\psi-r_o,\ r(\psi,A)\sin\psi\right).
}
$$

Therefore:

<a id="eq-064"></a>

$$
\boxed{H(A)=\sup_{\psi}\beta(\psi,A).}
$$

**Lunar curvature and observer height are already included in this geometry.** The formula is exact within the radial surface model; its numerical accuracy depends on the DEM and the search for the upper bound.

### 8.4. Deriving the curvature correction

For small $\psi$:

<a id="eq-065"></a>

$$
\cos\psi\approx1-\frac{\psi^2}{2},\qquad
\sin\psi\approx\psi.
$$

Define the arc length on the reference sphere as $d=R\psi$. When elevations are small relative to $R$, the vertical and horizontal components are approximately:

<a id="eq-066"></a>

$$
U\approx z-z_0-h-\frac{d^2}{2R},\qquad L\approx d.
$$

Hence:

<a id="eq-067"></a>

$$
\boxed{
\beta\approx\operatorname{atan2}
\left(z-z_0-h-\frac{d^2}{2R},\ d\right).
}
$$

The term $d^2/(2R)$ represents the drop of the spherical surface below the tangent plane.

For example, with $z_0=0$, $h=2$ m, and a summit $1000$ m high at distance $d=20\,000$ m, the flat approximation gives:

<a id="eq-068"></a>

$$
\arctan\frac{1000-2}{20\,000}\approx2.857^\circ.
$$

The exact spherical formula with $R=1\,737\,400$ m gives:

<a id="eq-069"></a>

$$
\boxed{\beta\approx2.526^\circ.}
$$

The difference is about $0.331^\circ$, and the approximate surface drop is:

<a id="eq-070"></a>

$$
\frac{20\,000^2}{2\cdot1\,737\,400}\approx115.1\ \text{m}.
$$

When using exact three-dimensional coordinates or the formula involving $\sin\psi,\cos\psi$, do not subtract $d^2/(2R)$ again: that would count the same curvature twice.

### 8.5. Why the horizon can be negative

Consider a smooth sphere of radius $R$ and an observer at height $h>0$. The horizon ray is tangent to the sphere, and the radius at the tangency point is perpendicular to that ray. The resulting right triangle has hypotenuse $R+h$ and one leg $R$.

For the central angle to the tangency point:

<a id="eq-071"></a>

$$
\cos\psi_h=\frac{R}{R+h},\qquad
\psi_h=\arccos\frac{R}{R+h}.
$$

The direction toward that point is below the observer's horizontal plane by the same angle:

<a id="eq-072"></a>

$$
\boxed{H_{\mathrm{sphere}}=-\arccos\frac{R}{R+h}.}
$$

For $h=2$ m:

<a id="eq-073"></a>

$$
H_{\mathrm{sphere}}\approx-0.08694^\circ,
\qquad R\psi_h\approx2.636\ \text{km}.
$$

A point source at elevation $-0.05^\circ$ is therefore still visible. Applying `horizon = max(horizon, 0)` would artificially block part of the sky.

For $h=0$ and $0<\psi<\pi$:

<a id="eq-074"></a>

$$
\beta(\psi)=\operatorname{atan2}(\cos\psi-1,\sin\psi)
=-\frac{\psi}{2}.
$$

All distant points lie below the horizontal plane, but their elevation angles approach zero as $\psi\to0$. Therefore:

<a id="eq-075"></a>

$$
\sup_{\psi>0}\beta(\psi)=0.
$$

Sparse sampling can produce a negative maximum even in this limiting case. This is why a finite sampled maximum must be distinguished from the continuous supremum.

<a id="terrain"></a>

## 9. Terrain coverage and resolution

### 9.1. How far to search for obstructions

A fixed radius of 5 or 20 km does not guarantee sufficient coverage. A distant high mountain may raise the horizon even after the nearby smooth surface has disappeared behind lunar curvature.

Assume global bounds are known for the entire adopted model:

<a id="eq-076"></a>

$$
r_{\min}\le R+z(\varphi,\lambda)\le r_{\max}.
$$

The sphere of radius $r_{\min}$ must lie entirely inside the opaque Moon, and the sphere of radius $r_{\max}$ must contain the entire surface. The observer lies at radius $r_o\ge r_{\min}$.

A tangent from the observer to the inner sphere defines the central angle:

<a id="eq-077"></a>

$$
\alpha=\arccos\frac{r_{\min}}{r_o}.
$$

For the highest permitted point, the corresponding angle is:

<a id="eq-078"></a>

$$
\gamma=\arccos\frac{r_{\min}}{r_{\max}}.
$$

In the limiting configuration, the two tangents lie on the same straight line. Their central angles add to give a sufficient coverage limit:

<a id="eq-079"></a>

$$
\boxed{
\psi_{\mathrm{cut}}=
\arccos\frac{r_{\min}}{r_o}
+\arccos\frac{r_{\min}}{r_{\max}},
\qquad
d_{\mathrm{cut}}=R\psi_{\mathrm{cut}}.
}
$$

Beyond this central angle, the segment from the observer to a summit intersects the opaque inner sphere. That summit can no longer raise the visible horizon. This is a geometric derivation within the adopted model.

For the illustrative bounds:

<a id="eq-080"></a>

$$
r_{\min}=R,\quad r_{\max}=R+1000\ \text{m},\quad r_o=R+2\ \text{m}
$$

the result is $d_{\mathrm{cut}}\approx61.57$ km. This example uses specified elevation bounds; it is not a universal radius for loading lunar terrain.

**The bounds must apply to the entire model, not just the fragment already loaded.** If the DEM contains negative elevations, $r_{\min}=R$ cannot be assumed: part of the reference sphere may lie above the actual ground.

### 9.2. Avoiding missed narrow ridges

A simple numerical method samples azimuths and searches for the highest terrain elevation angle along each direction. An initial step such as $0.05^\circ$ must be checked by convergence.

An obstruction of transverse width $w$ at distance $d$ subtends approximately:

<a id="eq-081"></a>

$$
\Delta A\approx\frac wd
\qquad\text{in radians}.
$$

For $w=20$ m and $d=20$ km, $\Delta A\approx0.057^\circ$. A sparse azimuth grid can miss such obstructions.

When constructing the profile:

- traverse intersected DEM cells using the chosen surface interpolation;
- refine the angular grid where the horizon changes sharply;
- check stability as the spatial step is reduced;
- close the profile periodically between $360^\circ$ and $0^\circ$;
- preserve high terrain when reducing the detail of distant regions;
- account for map projection geometry: a great circle is generally curved on a planar map;
- treat missing samples as unavailable data rather than zero elevation.

Taking a maximum only over pixel centres and rounding their azimuths can create false gaps. If data are insufficient for a direction or the required coverage, mark the result as incomplete.

An alternative is a triangular surface mesh with ray intersection tests. SPICE supports such models through [DSK](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/dsk.html). This removes the additional azimuth grid while retaining dependence on the quality of the underlying surface model.

<a id="ephemeris"></a>

## 10. Sun and Earth positions with SPICE

[`spkcpo`](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/spkcpo_c.html) supports an observer at fixed coordinates in a lunar frame. The calling program supplies the observer position, and the function returns the target state relative to it. The Python interface is described in the [SpiceyPy documentation](https://spiceypy.readthedocs.io/en/stable/documentation.html#spiceypy.spiceypy.spkcpo).

Before calculation, load a consistent set of SPICE kernels for time, body trajectories, lunar orientation, and frame definitions. Kernel coverage must include the analysis period and any additional epochs required by the corrections.

An example of obtaining a vector after loading the kernels:

```python
import numpy as np
import spiceypy as spice


# Block: Observer-relative body vector
def body_vector_m(
    target: str,
    et: float,
    observer_m: np.ndarray,
    frame: str,
) -> np.ndarray:

    state, _ = spice.spkcpo(
        target=target,
        et=et,
        outref=frame,
        refloc="OBSERVER",
        abcorr="CN+S",
        obspos=np.asarray(observer_m, dtype=np.float64) / 1000.0,
        obsctr="MOON",
        obsref=frame,
    )
    return np.asarray(state[:3]) * 1000.0
```

The same procedure can be wrapped for both bodies. The observer position, epoch, and frame are explicit arguments:

```python
# Block: Sun and Earth vectors
def sun_and_earth_vectors_m(et, observer_m, frame):
    sun_vector = body_vector_m("SUN", et, observer_m, frame)
    earth_vector = body_vector_m("EARTH", et, observer_m, frame)
    return sun_vector, earth_vector
```

Here `observer_m` is the spacecraft position relative to the lunar centre, and `frame` is the lunar frame consistent with the DEM. Convert UTC with the standard SPICE routine to obtain `et`, expressed in TDB seconds past J2000.

`refloc="OBSERVER"` evaluates the output frame at the observation epoch. `CN+S` applies converged light-time correction and stellar aberration. These options are defined in the [NAIF documentation](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/spkcpo_c.html).

The returned vector already points from the observer to the target. Project it onto ENU without subtracting $\mathbf p$ again. Comparisons with another calculation must use matching observer positions, times, frames, and correction settings.

Libration and changing lunar orientation follow from ephemerides and frame transformations. Do not replace the Earth direction with a fixed point.

<a id="solar-disc"></a>

## 11. The solar disc and its visible fraction

### 11.1. Deriving angular radius

A point model checks only the solar centre. Near the lunar horizon, the centre may be blocked while the upper part of the disc still provides light. Illumination calculations therefore need the source's finite angular size.

Let a spherical body have physical radius $R_B$, with observer-to-centre distance:

<a id="eq-082"></a>

$$
D_B(t)=\|\mathbf v_B(t)\|.
$$

The ray to the apparent limb is tangent to the sphere. The radius at the tangency point is perpendicular to the ray, so $R_B$ is the opposite leg and $D_B$ the hypotenuse of a right triangle. If $\rho_B$ is the angle between the centre and limb directions:

<a id="eq-083"></a>

$$
\sin\rho_B=\frac{R_B}{D_B}.
$$

For $D_B>R_B$, this gives:

<a id="eq-084"></a>

$$
\boxed{\rho_B(t)=\arcsin\frac{R_B}{\|\mathbf v_B(t)\|}.}
$$

The full angular diameter is $2\rho_B$. The radius and distance must use the same units.

For rounded illustrative values $R_B=700\,000$ km and $D_B=150\,000\,000$ km:

<a id="eq-085"></a>

$$
\rho_B\approx0.2674^\circ.
$$

If the centre of this disc is $0.20^\circ$ below a level horizon, its upper limb remains visible. These values illustrate the geometry; calculations use the ephemeris distance and the adopted physical radius.

### 11.2. Position relative to a straight boundary

First consider a small angular disc and a straight horizontal boundary in the local sky plane. Define the centre's elevation above this boundary:

<a id="eq-086"></a>

$$
\Delta=\varepsilon_S-H.
$$

Then:

<a id="eq-087"></a>

$$
\begin{aligned}
\Delta\le-\rho_S&\quad\Rightarrow\quad\text{disc fully blocked},\\
-\rho_S<\Delta<\rho_S&\quad\Rightarrow\quad\text{disc partially visible},\\
\Delta\ge\rho_S&\quad\Rightarrow\quad\text{disc fully visible}.
\end{aligned}
$$

This approximation provides a useful check. For an uneven ridge, test the boundary separately for each direction within the disc.

### 11.3. Deriving the visible area with an integral

In the local sky plane, define coordinates $x,y$ relative to the disc centre. All angles here are in radians. In the small-disc approximation:

<a id="eq-088"></a>

$$
x^2+y^2\le\rho_S^2.
$$

The centre lies $\Delta$ above the boundary. A point is visible precisely when:

<a id="eq-089"></a>

$$
y+\Delta>0\quad\Longleftrightarrow\quad y>-\Delta.
$$

At height $y$, the circle equation gives the two edges of a horizontal strip:

<a id="eq-090"></a>

$$
x=\pm\sqrt{\rho_S^2-y^2}.
$$

The strip width and area are:

<a id="eq-091"></a>

$$
w(y)=2\sqrt{\rho_S^2-y^2},
\qquad
dS=2\sqrt{\rho_S^2-y^2}\,dy.
$$

Under partial obstruction, add the strips from the horizon to the upper limb to obtain the visible area:

<a id="eq-092"></a>

$$
S_{\mathrm{vis}}=
\int_{-\Delta}^{\rho_S}2\sqrt{\rho_S^2-y^2}\,dy.
$$

To find the antiderivative, substitute:

<a id="eq-093"></a>

$$
y=\rho_S\sin\theta,
\qquad dy=\rho_S\cos\theta\,d\theta.
$$

On the relevant interval, $\cos\theta\ge0$. Use the double-angle identity:

<a id="eq-094"></a>

$$
2\cos^2\theta=1+\cos2\theta.
$$

The integrand becomes:

<a id="eq-095"></a>

$$
2\sqrt{\rho_S^2-y^2}\,dy
=2\rho_S^2\cos^2\theta\,d\theta
=\rho_S^2(1+\cos2\theta)\,d\theta.
$$

Integrate and substitute back:

<a id="eq-096"></a>

$$
F(y)=y\sqrt{\rho_S^2-y^2}
+\rho_S^2\arcsin\frac{y}{\rho_S}.
$$

At the upper limit, $F(\rho_S)=\pi\rho_S^2/2$. At the lower limit:

<a id="eq-097"></a>

$$
F(-\Delta)=-\Delta\sqrt{\rho_S^2-\Delta^2}
-\rho_S^2\arcsin\frac{\Delta}{\rho_S}.
$$

Subtract the lower value from the upper one. For $|\Delta|<\rho_S$, the visible area is:

<a id="eq-098"></a>

$$
S_{\mathrm{vis}}=F(\rho_S)-F(-\Delta)
=\frac{\pi\rho_S^2}{2}+\Delta\sqrt{\rho_S^2-\Delta^2}
+\rho_S^2\arcsin\frac{\Delta}{\rho_S}.
$$

Divide by the full area $\pi\rho_S^2$. Define the dimensionless quantity:

<a id="eq-099"></a>

$$
k=\frac{\Delta}{\rho_S}.
$$

The visible fraction is:

<a id="eq-100"></a>

$$
\boxed{
f_{\mathrm{flat}}=
\begin{cases}
0,& k\le-1,\\[4pt]
\displaystyle\frac12+
\frac{\arcsin k+k\sqrt{1-k^2}}{\pi},& -1<k<1,\\[8pt]
1,& k\ge1.
\end{cases}
}
$$

Checks:

<a id="eq-101"></a>

$$
\begin{aligned}
k=0&\quad\Rightarrow\quad f_{\mathrm{flat}}=0.5,\\
k=0.5&\quad\Rightarrow\quad f_{\mathrm{flat}}\approx0.8045,\\
k=-0.5&\quad\Rightarrow\quad f_{\mathrm{flat}}\approx0.1955.
\end{aligned}
$$

For example, with $\rho_S=0.30^\circ$, $H=2^\circ$, and $\varepsilon_S=1.85^\circ$:

<a id="eq-102"></a>

$$
k=\frac{1.85-2}{0.30}=-0.5.
$$

About $19.55\%$ of the disc area is visible. With uniform brightness, this is also the direct solar flux fraction in the small-disc approximation.

### 11.4. Integrating over an uneven horizon

Each disc point needs its own direction $\widehat{\mathbf s}(x,y,t)$, azimuth $A(x,y,t)$, and elevation $\varepsilon(x,y,t)$. Define the open-direction mask:

<a id="eq-103"></a>

$$
M_T(x,y,t)=\mathbf 1\!\left[\varepsilon(x,y,t)>H(A(x,y,t))\right]
=\begin{cases}
1,&\varepsilon(x,y,t)>H(A(x,y,t)),\\
0,&\text{otherwise}.
\end{cases}
$$

The indicator $\mathbf 1[\cdot]$ is one when the condition holds and zero otherwise. For disc $\mathcal D_S$:

<a id="eq-104"></a>

$$
\boxed{
f_T(t)=\frac{1}{\pi\rho_S^2}
\iint_{\mathcal D_S}M_T(x,y,t)\,dx\,dy.
}
$$

This generalizes the strip integral: it adds the areas of every open region, even with a complex boundary. Numerically, replace the integral with a sum:

<a id="eq-105"></a>

$$
\boxed{
f_T(t)\approx\frac{\sum_{j=1}^{N}w_jM_{T,j}(t)}{\sum_{j=1}^{N}w_j}.
}
$$

Each weight $w_j$ represents the area assigned to a sample. For equal-area samples:

<a id="eq-106"></a>

$$
f_T(t)\approx\frac1N\sum_{j=1}^{N}M_{T,j}(t)=\frac{N_{\mathrm{visible}}}{N}.
$$

### 11.5. Sampling uniformly over disc area

Uniform radial spacing puts too many samples near the centre. A circle of radius $r$ occupies fraction $r^2/\rho_S^2$ of the total area. A uniform variable $q\in[0,1]$ must therefore satisfy:

<a id="eq-107"></a>

$$
\frac{r_{\mathrm{sample}}^2}{\rho_S^2}=q
\quad\Rightarrow\quad
\boxed{r_{\mathrm{sample}}=\rho_S\sqrt q.}
$$

The polar angle $\gamma$ covers $[0,2\pi)$ uniformly. A deterministic equal-area sequence gives repeatable calculations. Start with 256–1024 samples and check convergence as the sample count increases, particularly during partial obstruction.

To turn disc samples into three-dimensional directions, define the centre direction:

<a id="eq-108"></a>

$$
\widehat{\mathbf s}=\frac{\mathbf v_S}{\|\mathbf v_S\|}.
$$

Choose two mutually perpendicular unit vectors $\mathbf b_1,\mathbf b_2$, both perpendicular to $\widehat{\mathbf s}$. For example, using an auxiliary unit vector $\mathbf k$ that is not parallel to $\widehat{\mathbf s}$:

<a id="eq-109"></a>

$$
\mathbf b_1=\frac{\mathbf k\times\widehat{\mathbf s}}
{\|\mathbf k\times\widehat{\mathbf s}\|},
\qquad
\mathbf b_2=\widehat{\mathbf s}\times\mathbf b_1.
$$

For coordinates on the unit planar disc:

<a id="eq-110"></a>

$$
x_j=\sqrt{q_j}\cos\gamma_j,
\qquad y_j=\sqrt{q_j}\sin\gamma_j
$$

construct a ray direction as:

<a id="eq-111"></a>

$$
\mathbf d_j=\widehat{\mathbf s}
+\tan\rho_S(x_j\mathbf b_1+y_j\mathbf b_2),
\qquad
\boxed{\widehat{\mathbf s}_j=\frac{\mathbf d_j}{\|\mathbf d_j\|}.}
$$

Limb samples have angular separation $\rho_S$ from the centre. Equal weights in this planar projection follow the adopted small-disc approximation. More accurate radiometry accounts for projection, solid angle, and brightness distribution.

Project every $\widehat{\mathbf s}_j$ onto ENU and compare it with $H(A_j)$. Checking the entire disc only against $H(A_S)$ beneath its centre misses variations in the ridge.

<a id="eclipse"></a>

## 12. Solar occultation by Earth

Earth can block the Sun even when the terrain leaves its direction open. In the basic geometric model, Earth is an opaque sphere of radius $R_E$. The same right-triangle derivation gives its angular radius:

<a id="eq-112"></a>

$$
\rho_E(t)=\arcsin\frac{R_E}{\|\mathbf v_E(t)\|},
\qquad
\widehat{\mathbf d}_E(t)=\frac{\mathbf v_E(t)}{\|\mathbf v_E(t)\|}.
$$

For a selected point on the solar disc, let $\alpha_j$ be its angular separation from the Earth centre. The dot product of unit vectors is the cosine of that angle:

<a id="eq-113"></a>

$$
\cos\alpha_j=\widehat{\mathbf s}_j\cdot\widehat{\mathbf d}_E.
$$

Since cosine decreases on $[0,\pi]$, the condition for falling inside the terrestrial disc is:

<a id="eq-114"></a>

$$
\alpha_j\le\rho_E
\quad\Longleftrightarrow\quad
\widehat{\mathbf s}_j\cdot\widehat{\mathbf d}_E\ge\cos\rho_E.
$$

For occultations viewed from the Moon, Earth is in front of the Sun, so this angular condition is sufficient within the adopted model. For arbitrary pairs of bodies, their distance ordering must also be checked.

The mask for a ray that is not blocked by Earth is:

<a id="eq-115"></a>

$$
M_{E,j}(t)=\mathbf 1\!\left[
\widehat{\mathbf s}_j(t)\cdot\widehat{\mathbf d}_E(t)<\cos\rho_E(t)
\right].
$$

A ray provides direct light only when it passes both above the terrain and outside the terrestrial disc. First multiply the masks of **the same ray**:

<a id="eq-116"></a>

$$
M_j(t)=M_{T,j}(t)M_{E,j}(t),
$$

Then calculate the final visible solar fraction:

<a id="eq-117"></a>

$$
\boxed{
f_S(t)\approx
\frac{\sum_{j=1}^{N}w_jM_{T,j}(t)M_{E,j}(t)}{\sum_{j=1}^{N}w_j}.
}
$$

Multiplying two already averaged fractions is generally incorrect. If both obstructions leave the same half of the disc open, the final fraction is $0.5$. If they leave opposite halves open, it is zero. Their product $0.5\cdot0.5=0.25$ is wrong in both cases.

This is geometric obstruction by an opaque sphere. Calculating light transmitted through Earth's atmosphere during an eclipse requires an additional physical model.

<a id="earth"></a>

## 13. Earth visibility and communications

The minimum version checks the direction toward the Earth centre:

<a id="eq-118"></a>

$$
g_E(t)=\varepsilon_E(t)-H(A_E(t)),
\qquad
\boxed{I_E(t)=\mathbf 1[g_E(t)>0].}
$$

Each current state dictionary stores `earth_center_visible` and `earth_clearance_rad`. The clearance is in radians. Convert it with `radians_to_degrees` when building a display value such as `earth_clearance_deg`; the unconverted field must not be labelled as degrees. If needed, calculate the terrain-visible terrestrial disc fraction $f_E(t)$ separately with `disc_terrain_fraction`.

Choose one visibility definition before comparing sites:

| Criterion | Condition | Meaning |
| --- | --- | --- |
| Earth centre visible | $g_E>0$ | The direction toward the centre is clear |
| Part of the disc visible | $f_E>0$ | At least some portion of Earth is visible |
| Required fraction visible | $f_E\ge f_{E,\min}$ | The selected geometric threshold is satisfied |
| Specified station visible | Test the station direction | A geometric line of sight to a specific object exists |

An uneven horizon requires different checks for the centre, limb, and a ground station. NASA notes that [visibility of any part of Earth can overestimate the availability of links to DSN stations](https://pgda.gsfc.nasa.gov/products/69).

For a station, calculate its position with Earth's rotation, the direction from the lunar spacecraft, obstruction by the Moon, and the station's own horizon constraints. Radio availability also requires antenna characteristics, pointing, frequency, power, and a link budget. The basic application metric describes geometric visibility.

<a id="power"></a>

## 14. From solar visibility to panel power

### 14.1. Derivation using effective area

Disc fraction $f_S$ is dimensionless. To obtain electrical power, specify:

| Quantity | Meaning and units |
| --- | --- |
| $S_p$ | Panel area, m² |
| $\eta$ | Conversion efficiency, between 0 and 1 |
| $I_0(t)$ | Solar irradiance on a surface perpendicular to the central ray, W/m² |
| $\mathbf m(t)$ | Unit normal to the active panel face |
| $\widehat{\mathbf s}(t)$ | Unit direction from the panel toward the Sun centre |

All vectors must use the same frame. If the normal is specified in ENU, transform it into global coordinates using $\mathbf B$.

Let $\theta$ be the angle between the panel normal and the Sun direction. By the definition of a dot product:

<a id="eq-119"></a>

$$
\mathbf m\cdot\widehat{\mathbf s}=\cos\theta.
$$

The ray bundle sees the panel projected onto a perpendicular plane. For the illuminated active face, that projected area is:

<a id="eq-120"></a>

$$
S_{\mathrm{effective}}=S_p\cos\theta.
$$

Irradiance multiplied by effective area gives incident power; multiplying by $\eta$ gives electrical power. For a small disc of uniform brightness with nearly constant incidence angle across it:

<a id="eq-121"></a>

$$
\boxed{
P(t)\approx\eta S_p I_0(t)f_S(t)
\max\!\left(0,\mathbf m(t)\cdot\widehat{\mathbf s}(t)\right).
}
$$

The maximum with zero represents a single-sided panel: this model generates no power from light incident on its back. At $\theta=60^\circ$, the projected area is half its value at normal incidence.

For a horizontal panel, $\mathbf m=\mathbf u$, so its dot product with the central direction equals $\sin\varepsilon_S$. The orientation factor becomes $\max(0,\sin\varepsilon_S)$.

If only the changing solar distance is considered, scale the irradiance using the inverse-square law:

<a id="eq-122"></a>

$$
I_0(t)=I_{\mathrm{ref}}
\left(\frac{D_{\mathrm{ref}}}{D_S(t)}\right)^2.
$$

Here $I_{\mathrm{ref}}$ is the specified reference irradiance at distance $D_{\mathrm{ref}}$. The law follows from distributing the same radiated power over a sphere of area $4\pi D^2$.

### 14.2. A more general power integral

When the incidence angle varies significantly across the disc, calculate each direction's contribution separately. Let $L(\widehat{\mathbf s},t)$ be radiance in W/(m²·sr), $d\Omega$ an element of solid angle, and $M$ the combined terrain and Earth mask. Then:

<a id="eq-123"></a>

$$
\boxed{
P(t)=\eta S_p\int_{\Omega_S}
L(\widehat{\mathbf s},t)M(\widehat{\mathbf s},t)
\max(0,\mathbf m(t)\cdot\widehat{\mathbf s})\,d\Omega.
}
$$

Each open direction contributes flux with its own incidence cosine. The relationship between radiance, solid angle, and incident flux is described in the [Cambridge radiometry material](https://www.cl.cam.ac.uk/teaching/1718/AdvGraph/01_Reflection_models.pdf).

Near grazing incidence, this integral is more useful than the centre-direction approximation. Temperature, dust, panel degradation, and electronic losses can be included in a separate efficiency model.

<a id="events"></a>

## 15. Finding rises, sets, and window boundaries

### 15.1. The equation to solve

For a point-like body, visibility changes at a zero of its angular clearance:

<a id="eq-124"></a>

$$
g_B(t)=\varepsilon_B(t)-H(A_B(t)),
\qquad
\boxed{g_B(t_*)=0.}
$$

A transition from negative to positive values means appearance; the reverse means disappearance. Touching zero without changing state does not itself create an interval of positive duration.

For an operational sunlight window, choose a threshold $0<f_{\min}\le1$:

<a id="eq-125"></a>

$$
g_S(t)=f_S(t)-f_{\min},
\qquad
I_S(t)=\mathbf 1[f_S(t)\ge f_{\min}].
$$

For example, $f_{\min}=0.8$ requires at least $80\%$ of the disc to be visible. For any direct sunlight, use the separate criterion $f_S>0$: $f_S\ge0$ would also hold in complete darkness.

For a panel, a positive power threshold can similarly define $I_S=\mathbf 1[P\ge P_{\min}]$. Store the criterion definition with the result.

### 15.2. Deriving a linear transition time estimate

Let the endpoint values on a short interval be:

<a id="eq-126"></a>

$$
g_0=g(t_0),\qquad g_1=g(t_1).
$$

Approximate the function by a straight line:

<a id="eq-127"></a>

$$
g(t)\approx g_0+(g_1-g_0)\frac{t-t_0}{t_1-t_0}.
$$

At the transition, set the value to zero:

<a id="eq-128"></a>

$$
0=g_0+(g_1-g_0)\frac{t_*-t_0}{t_1-t_0}.
$$

Move $g_0$ to the other side and divide by $g_1-g_0\ne0$:

<a id="eq-129"></a>

$$
\frac{t_*-t_0}{t_1-t_0}=-\frac{g_0}{g_1-g_0}.
$$

Therefore:

<a id="eq-130"></a>

$$
\boxed{t_*\approx t_0-\frac{g_0}{g_1-g_0}(t_1-t_0).}
$$

For example, the observed endpoint values are:

<a id="eq-131"></a>

$$
\begin{aligned}
g(12{:}00)&=-0.2^\circ,\\
g(13{:}00)&=+0.4^\circ.
\end{aligned}
$$

Reaching zero requires one third of the total change:

<a id="eq-132"></a>

$$
\frac{0.2}{0.4-(-0.2)}\cdot60\ \text{min}=20\ \text{min}.
$$

This gives $t_*\approx12{:}20$. It is an initial estimate; for a complex horizon, recompute the function within the interval.

### 15.3. Detecting and refining events

The target application procedure is:

1. Evaluate the state on an initial time grid, for example every 5 minutes.
2. Identify state changes and subdivide intervals where short windows may occur.
3. For each detected transition, recompute the geometry inside its bracket until the chosen tolerance is reached, for example 30–60 seconds.
4. Sort the boundaries and assemble continuous intervals with the same state.
5. In the application output, record whether the first and last intervals are clipped by the analysis boundaries.

These numbers are initial settings. The detection step depends on event duration and motion relative to horizon features. Two transitions within one step can be missed: endpoint states may match even though a short window occurred between them.

For continuous $g_E(t)$ with opposite signs at the interval endpoints, bisection or `scipy.optimize.brentq` is appropriate. With a finite ray sample, $f_S$ changes in steps. Refine the selected state transition in that case; increasing the ray count and checking convergence remain separate from the time tolerance.

The detection step and the refinement accuracy of an already detected boundary are different settings. This distinction is also discussed in the [NAIF occultation search documentation](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/gfoclt_c.html).

An angular error can be related to event timing. Near a simple root:

<a id="eq-133"></a>

$$
g(t_*+\delta t)\approx g(t_*)+g'(t_*)\delta t.
$$

For a geometric error $\delta g$, the magnitude of the time shift is approximately:

<a id="eq-134"></a>

$$
\boxed{|\delta t|\approx\frac{|\delta g|}{|g'(t_*)|}.}
$$

When motion past a ridge is nearly tangential and slow, even a small elevation error can substantially shift the event. A one-second numerical root tolerance therefore does not imply a one-second prediction accuracy.

<a id="metrics"></a>

## 16. Durations, energy, and joint windows

### 16.1. Duration of a selected state

Let the analysis period be $[t_0,t_1]$. Define the selected state explicitly:

<a id="eq-135"></a>

$$
I_S(t)=\begin{cases}
1,&\text{illumination criterion holds},\\
0,&\text{otherwise}.
\end{cases}
$$

This criterion may be a positive visible-disc threshold or a positive power threshold. Over a small interval $dt$, suitable conditions add $I_S(t)\,dt$ to the duration. Adding all contributions gives:

<a id="eq-136"></a>

$$
\boxed{T_S=\int_{t_0}^{t_1}I_S(t)\,dt.}
$$

If non-overlapping windows $[a_k,b_k]$ have already been clipped to the analysis period, the indicator is one throughout each window. Therefore:

<a id="eq-137"></a>

$$
\boxed{T_S=\sum_k(b_k-a_k).}
$$

The fraction of time with suitable conditions is:

<a id="eq-138"></a>

$$
F_S=\frac{T_S}{t_1-t_0}.
$$

The same derivation applies to Earth visibility:

<a id="eq-139"></a>

$$
T_E=\int_{t_0}^{t_1}I_E(t)\,dt.
$$

### 16.2. Longest continuous periods

For sunlight windows:

<a id="eq-140"></a>

$$
\boxed{T_{S,\max}=\max_k(b_k-a_k).}
$$

If there are no suitable windows, take the duration as zero. To calculate interruptions, construct the complement of the sunlight windows within $[t_0,t_1]$. Let its intervals be $[c_l,d_l]$. Then:

<a id="eq-141"></a>

$$
\boxed{T_{\mathrm{gap},\max}=\max_l(d_l-c_l).}
$$

The longest continuous Earth visibility period and its longest interruption are obtained in the same way.

With $f_{\min}>0$, an interruption means the selected criterion is not satisfied. Complete geometric darkness is the separate state $f_S=0$ and may last less than a threshold-based interruption.

Counting suitable samples does not give an exact duration. Samples at 12:00, 13:00, and 14:00 span two hours between the first and last measurements, while the true window boundaries may lie outside them. An adaptive grid makes it even more important to use actual elapsed times.

If a window continues beyond the start or end of the analysis, its duration inside the period is known but its full duration is not. An application should attach `clipped_start` and `clipped_end` flags. The current helpers return interval bounds and do not attach these flags automatically.

### 16.3. Equivalent fully visible disc time

The indicator describes threshold satisfaction, while the disc fraction describes how much of the source is visible. Over a short interval, the equivalent full-disc contribution is $f_S(t)\,dt$. Therefore:

<a id="eq-142"></a>

$$
\boxed{T_{\mathrm{eq}}=\int_{t_0}^{t_1}f_S(t)\,dt.}
$$

If the disc is fully visible for two hours and half visible for one more hour:

<a id="eq-143"></a>

$$
T_{\mathrm{eq}}=1\cdot2+0.5\cdot1=2.5\ \text{h}.
$$

The mean visible fraction during the period is:

<a id="eq-144"></a>

$$
\overline f_S=\frac{T_{\mathrm{eq}}}{t_1-t_0}.
$$

This quantity does not include panel orientation, efficiency, or changing solar irradiance. It is useful for geometric comparisons of sites.

### 16.4. Electrical energy

Power is energy per unit time, so $dW=P(t)\,dt$. Integration gives:

<a id="eq-145"></a>

$$
\boxed{W=\int_{t_0}^{t_1}P(t)\,dt.}
$$

With power in watts and time in seconds, the result is in joules. Integrating with time in hours gives watt-hours:

<a id="eq-146"></a>

$$
1\ \text{W}\cdot\text{h}=3600\ \text{J}.
$$

For numerical integration on a nonuniform time grid, the trapezoidal rule gives, for example:

<a id="eq-147"></a>

$$
W\approx\sum_i\frac{P(t_i)+P(t_{i+1})}{2}(t_{i+1}-t_i).
$$

Integrate $f_S$ similarly to obtain $T_{\mathrm{eq}}$. Refine the grid near visibility changes and check integral convergence.

When values are known to be constant on supplied time intervals, `time_integral`, `equivalent_full_disc_time`, and `electrical_energy` also accept `method="interval"`. Pass one more time edge than interval values. The calculation sums each interval value multiplied by its actual duration. For example, time edges `[0, 7200, 10800]` seconds and fractions `[1, 0.5]` give exactly 9000 seconds, or 2.5 equivalent hours. This interval representation is different from supplying point samples to the trapezoidal rule.

### 16.5. Joint sunlight and Earth visibility windows

Both conditions must hold at the same time. For binary indicators, logical AND is multiplication:

<a id="eq-148"></a>

$$
I_{\mathrm{joint}}(t)=I_S(t)I_E(t).
$$

The total duration of simultaneous conditions is therefore:

<a id="eq-149"></a>

$$
\boxed{
T_{\mathrm{joint}}=\int_{t_0}^{t_1}I_S(t)I_E(t)\,dt.
}
$$

With already computed windows, calculate their intersection. A sunlight window $[a,b]$ and an Earth visibility window $[c,d]$ overlap for:

<a id="eq-150"></a>

$$
\Delta t_{\cap}=\max\!\left(0,\min(b,d)-\max(a,c)\right).
$$

Add the lengths of the non-overlapping joint windows. Multiplying time fractions $F_SF_E$ ignores window alignment and generally gives the wrong result.

### 16.6. Time until the next change

If the current time inside the analysis period is $t$, and the next boundary of the requested state is $t_{\mathrm{next}}$, then:

<a id="eq-151"></a>

$$
\boxed{\Delta t_{\mathrm{next}}=t_{\mathrm{next}}-t.}
$$

Return the duration with an event type: sunlight appearing or disappearing, or the Earth direction opening or closing. If no event occurs before the analysis ends, report its absence within this period.

<a id="architecture"></a>

## 17. Computational core structure

### 17.1. Responsibilities

All computational formulas remain in [mini_model.py](mini_model.py). The following responsibilities are separate calculation blocks inside that file.

| Calculation group | Responsibility |
| --- | --- |
| Terrain | Supplied elevations, coverage bounds, and surface directions |
| Geometry | Observer position, ENU basis, projections, azimuth, and elevation |
| Horizon | Sampled profile construction, interpolation, and angular clearance |
| Ephemerides | Observer-relative body vectors and optional SPICE access |
| Visibility and power | Solar and terrestrial discs, combined masks, and panel power |
| Events and metrics | Transitions, continuous windows, durations, and energy |

The combined calculation receives site geometry, a time array, observer-relative body vectors, a horizon function, and numerical settings. Prepare the fixed geometry once, then apply the visibility formulas at each time.

### 17.2. Formula implementation by calculation block

[mini_model.py](mini_model.py) implements the computational expressions and their numerical counterparts in Python and NumPy. Input values are function arguments; importing the file does not download data or run a calculation. Intermediate derivation steps and identities are identified separately in the formula audit. Comments in the code identify only block names.

| Block | Implemented calculations |
| --- | --- |
| 1 | Degree and radian conversion, vector normalization |
| 2 | Radial directions, spherical coordinates, ground and observer positions |
| 3 | Coordinate derivatives, terrain derivatives, east, north, and up |
| 4 | XYZ to ENU, ENU to XYZ, observer-relative body vectors |
| 5 | Azimuth, elevation, the equivalent sine formula, horizontal components |
| 6 | Great-circle terrain directions, exact terrain elevation, observer height sensitivity |
| 7 | Sampled horizon maxima, periodic interpolation, angular clearance, terrain masks |
| 8 | Curvature drop, approximate terrain elevation, smooth-sphere horizon and distance |
| 9 | Terrain coverage bound, feature angular width, elevation uncertainty |
| 10 | Optional SPICE body vectors and angular body radii |
| 11 | Circular strip width, area antiderivative, visible disc area and fraction |
| 12 | Equal-area disc samples, ray directions, weighted visibility integral, any body's terrain-visible disc fraction |
| 13 | Earth occultation, combined masks, solar fraction, Earth centre visibility |
| 14 | Inverse-square irradiance, projected area, approximate power, radiance quadrature |
| 15 | Illumination, complete darkness, point visibility, power threshold, and joint indicators |
| 16 | Linear crossing times, continuous root refinement, step-state refinement |
| 17 | Threshold crossings and continuous windows from sampled values |
| 18 | Total and longest durations, complementary and intersecting windows, next-event time |
| 19 | Equivalent full-disc time, mean fraction, electrical energy, timing uncertainty |
| 20 | Combined evaluation using the preceding formulas and supplied input arrays |

The base dependency is NumPy. `body_vector_from_spice` additionally requires SpiceyPy and a consistent kernel set loaded by the caller. It is optional when observer-relative vectors have already been supplied.

The future inputs to `analyze` are:

| Input | Definition |
| --- | --- |
| Site geometry | Latitude and east longitude in degrees; reference radius, ground elevation, and observer height in metres |
| `horizon` | A callable giving horizon elevation in radians for azimuths in radians; `make_horizon` constructs it from prepared samples |
| `times_s` | Strictly increasing elapsed times in seconds, at least two samples |
| `sun_vectors_m`, `earth_vectors_m` | Arrays of shape `(number of times, 3)`, already relative to the observer and expressed in the same lunar frame as the site |
| `sun_radius_m`, `earth_radius_m` | Physical radii adopted for the two spherical bodies |
| Numerical settings | Disc sample count and minimum visible solar fraction |
| Optional panel inputs | Area in m², efficiency, unit normal in ENU, and irradiance in W/m², either scalar or one value per time |

If the horizon has not been prepared, `build_sampled_horizon` accepts azimuth samples, central-angle scan samples, and an `elevation_at(latitude_rad, longitude_rad)` data reader. It explicitly computes the terrain directions, converts them to coordinates, evaluates the supplied elevation function, and takes the maximum terrain angle for each azimuth. The ground elevation, reference radius, observer position, and DEM must use the same frame and radial elevation convention.

The code uses a finite terrain scan and a finite disc sample. `windows_from_samples` uses linear interpolation between sampled threshold margins; `analyze` returns durations and energy under this approximation. Spatial convergence and short-event detection follow sections 9 and 15. When fresh evaluations at arbitrary times become available, `refine_transition` and `refine_state_transition` refine detected continuous or discrete-state boundaries. `time_to_next_event` accepts actual event times, excluding boundaries caused only by clipping the analysis period.

Formula checks are in [test_mini_model.py](test_mini_model.py). Run them with `python3 -B -m unittest -v test_mini_model.py`. Their synthetic values check the mathematics and do not represent mission observations.

### 17.3. Requirements for caching and repeated comparisons

The current code does not implement a persistent horizon cache. When one is added, its key must include coordinates, observer height, reference radius, frame, DEM version, coverage, and spatial calculation settings. The date is excluded: terrain relative to a stationary observer does not change.

Reuse $H(A)$ when comparing different dates. Recompute the horizon when the site, panel height, or terrain model changes. Prepare two profiles when the panel and antenna occupy different points.

An integration should preserve units, state criteria, DEM version, kernel names and versions, SPICE corrections, disc sampling parameters, and spatial and temporal tolerances with each result. These are requirements for reproducible mission comparisons. The current `analyze` return value contains numeric states, intervals, and metrics, but no metadata object.

### 17.4. Virtual environment and reproducible formula audit

The local Python environment is `.venv`. [requirements.txt](requirements.txt) pins NumPy to the version used for the checks. The optional SPICE wrapper additionally requires SpiceyPy and caller-provided kernels.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -B verify_formulas.py
```

[FORMULA_AUDIT.md](FORMULA_AUDIT.md) maps all 154 displayed equation blocks individually to source functions and executable evidence. It separates direct calculations, numerical approximations, derivation steps, identities, definitions, examples, and external inputs. The verifier checks that the equations match the reviewed fingerprint, that every equation has exactly one mapping, and that all referenced functions and tests exist, then runs both test suites. Tests validate the stated examples and properties; they do not establish that finite sampling captures every possible terrain feature or event.

The verifier also remains in one file, [verify_formulas.py](verify_formulas.py). Named records describe equations, formula specifications, source definitions, and test results. Parsing, validation, test execution, and report rendering are separate functions; `verify` only coordinates those stages. Source indexing preserves class-qualified method names. Call tracing uses the standard library and restores an existing trace handler after success or failure. `python -B verify_formulas.py --check` performs the checks without rewriting the report. The audit validates the registry and runs executable evidence; it does not symbolically prove the equivalence of arbitrary LaTeX and Python expressions.

### 17.5. Current return values and integration boundary

`analyze` returns a dictionary with `observer_m`, `basis`, `times_s`, `states`, `sun_windows`, `earth_windows`, `joint_windows`, `dark_windows`, `sun_gaps`, `earth_gaps`, `metrics`, `power_w`, and `energy`. Each item in `states` stores the current angular values in radians, the Earth-centre flag, the visible fractions, the sampled solar rays, and their combined open mask.

| Capability | Current implementation |
| --- | --- |
| Formula calculations from supplied values | Implemented in `mini_model.py` |
| Horizon from supplied elevation samples | `build_sampled_horizon`; a finite scan with caller-provided coverage and elevation access |
| Sun and Earth vectors | Supplied arrays, or the optional `body_vector_from_spice` wrapper after the caller loads kernels |
| Time windows | Threshold crossings linearly interpolated from the supplied time series |
| Refined transition times | Separate `refine_transition` and `refine_state_transition` functions; not automatically called by `analyze` |
| Panel power | Central-direction approximation in `analyze`; general radiance quadrature is a separate function |
| Energy and equivalent disc time | Trapezoidal integration in `analyze`; interval integration is available through the standalone integral functions |
| UTC conversion, actual DEM loading, and kernel selection | Caller or future data integration |
| Caching, output metadata, clipped-window flags, and a user interface | Integration requirements, not current return fields |

When panel inputs are absent, `power_w` and `energy` are `None`, not zero. A geometric Earth visibility window describes an open direction; availability of a specific communications link requires the additional station and radio calculations described in section 13.

<a id="validation"></a>

## 18. Model validation and accuracy

### 18.1. Checks with known answers

| Check | Expected result |
| --- | --- |
| ENU basis | Unit lengths, zero mutual dot products, and $\mathbf e\times\mathbf n=\mathbf u$ |
| Forward and inverse transformations | $\mathbf B^{\mathsf T}\mathbf B=\mathbf I$ and recovery of the original vector |
| Numerical example in section 7 | $E=1$, $N=\sqrt3$, $U=2$, $A=30^\circ$, $\varepsilon=45^\circ$ |
| Smooth sphere | $H=-\arccos(R/(R+h))$ for a DEM with zero elevation |
| Constant nonzero DEM | The smooth-sphere formula uses the actual radius $R+z_0$ |
| Artificial ridge | The source becomes blocked at the predicted elevation angle |
| Crossing north | No artificial jump between $359.99^\circ$ and $0.01^\circ$ |
| Increasing observer height | The horizon does not rise at a fixed azimuth |
| Straight solar disc boundary | Numerical visibility converges to the circular-segment formula in section 11 |
| Combined masks | Identical and opposite open halves give $0.5$ and $0$, respectively |
| Short window | A sufficiently fine search detects it and refinement preserves its duration |
| Integrals | $0\le T_{\mathrm{eq}},T_S,T_E\le t_1-t_0$ and $T_{\mathrm{joint}}\le\min(T_S,T_E)$ |

For a constant DEM elevation $z_0$, the analytical horizon is:

<a id="eq-152"></a>

$$
H=-\arccos\frac{R+z_0}{R+z_0+h}.
$$

Monotonicity with observer height follows directly from the terrain formula. For a fixed point with $0<\psi<\pi$:

<a id="eq-153"></a>

$$
\frac{\partial\beta}{\partial r_o}=
-\frac{r\sin\psi}
{(r\cos\psi-r_o)^2+(r\sin\psi)^2}<0.
$$

Raising the observer decreases the elevation angle of each such point; their upper bound therefore cannot increase either.

Celestial directions can also be compared with [JPL Horizons](https://ssd.jpl.nasa.gov/horizons/manual.html), using matching times, observer positions, frames, and corrections. This comparison checks ephemerides and transformations; terrain requires separate validation.

### 18.2. Sources of uncertainty

The main error sources are DEM elevations and georeferencing, missing data, surface interpolation, azimuth sampling, solar disc sampling, the event detection step, and ephemeris settings.

For a small obstruction height error $\delta z$ at distance $d$ and small elevation angles, a useful estimate is:

<a id="eq-154"></a>

$$
\delta\beta\approx\frac{\delta z}{d}.
$$

This follows from $\beta\approx\arctan(\Delta z/d)$ when the height-to-distance ratio is small. For example, a 1 m error at 1 km corresponds to about $0.057^\circ$. Nearby ridges therefore require particularly accurate terrain data.

A practical convergence check reduces the spatial and temporal steps, increases the number of disc samples, and compares window boundaries, durations, and integrated metrics. Check narrow obstructions, nearly tangential passages, and short windows separately.

Distinguish source surface uncertainty, numerical discretization, and the refinement tolerance of a detected event. Reducing one tolerance does not remove the other errors.

### 18.3. Conditions for mathematical consistency

The derived east, north, and radial up directions, ENU matrix, azimuth, and elevation are mutually consistent. The complete calculation retains these conditions:

- columns of $\mathbf B$ transform ENU into XYZ; rows of $\mathbf B^{\mathsf T}$ transform XYZ into ENU;
- subtract the observer position exactly once, and only from a lunar-centre-relative vector;
- use matching latitude, height, and frame definitions for the DEM and ephemerides;
- account for curvature once and preserve negative horizon elevations;
- account for disc size and each sample's azimuth during partial obstruction;
- combine terrain and Earth masks before averaging;
- calculate durations from interval boundaries and actual elapsed time;
- define disc visibility, available sunlight, panel power, and energy separately.

<a id="visualization"></a>

## 19. Presenting results in the application

The user selects a site, observer height, and analysis period. Present the computed results through linked views:

- **Site map.** Coordinates, surrounding terrain, and the area covered by the data.
- **Sky profile.** Azimuth on the horizontal axis, elevation on the vertical axis, $H(A)$, and Sun and Earth trajectories. Show the solar disc size.
- **Timeline.** Visible solar fraction, selected sunlight windows, Earth visibility, and their intersections on a shared time axis.
- **Scenario metrics.** Total durations, longest interruption, next transitions, and $T_{\mathrm{eq}}$. Include power and energy when panel parameters are specified.
- **Site and date comparison.** Matching metrics for each scenario, with thresholds and analysis periods stated explicitly.

Selecting a time on the timeline updates both body positions and their terrain clearance in the sky profile. This explains why a window begins or ends.

A three-dimensional surface and an animation of body motion can help explain the geometry. Also encode timeline states with text or shapes so that they remain distinguishable without relying on colour alone.

Mark windows clipped by the analysis period and results with incomplete DEM coverage beside the affected values. The label "geometric Earth visibility" preserves the metric's meaning when comparing it with communications to a specific station.

<a id="references"></a>

## 20. References and further reading

| Source | Purpose |
| --- | --- |
| [NASA LOLA Lunar Polar Illumination](https://pgda.gsfc.nasa.gov/products/69) | Polar illumination, reference sphere, and terrestrial disc visibility definitions |
| [NASA LOLA South Pole Site DEMs](https://pgda.gsfc.nasa.gov/products/78) | Detailed digital elevation models for selected sites |
| [NASA LOLA South Polar DEM](https://pgda.gsfc.nasa.gov/products/90) | Regional terrain and its coordinate frame |
| [NAIF SPICE `latrec`](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/latrec_c.html) | Spherical coordinates, planetocentric latitude, and east longitude |
| [ESA Navipedia ECEF and ENU](https://gssc.esa.int/navipedia/index.php/Transformations_between_ECEF_and_ENU_coordinates) | ENU basis, transformation matrices, azimuth, and elevation |
| [University of Alberta Parametric Surfaces](https://sites.ualberta.ca/~vbouchar/MATH215/section_parametric_surfaces.html) | Parameter derivatives as tangent directions |
| [University of Illinois Spherical Coordinates](https://dynamicref.web.engr.illinois.edu/rvs.html) | Spherical basis; replace the course's polar angle with $\pi/2-\varphi$ |
| [NAIF SPICE `spkcpo`](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/spkcpo_c.html) | Target vectors relative to an observer fixed in a specified frame |
| [SpiceyPy `spkcpo`](https://spiceypy.readthedocs.io/en/stable/documentation.html#spiceypy.spiceypy.spkcpo) | Python interface for the calculation |
| [NAIF Lunar Frame Kernel](https://naif.jpl.nasa.gov/pub/naif/generic_kernels/fk/satellites/moon_de440_250416.tf) | Lunar frame definitions and aliases; choose a realization consistent with the DEM |
| [NAIF DSK](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/req/dsk.html) | Surface models and terrain ray intersections |
| [NAIF SPICE `gfoclt`](https://naif.jpl.nasa.gov/pub/naif/toolkit_docs/C/cspice/gfoclt_c.html) | Occultation searches, detection steps, and boundary refinement |
| [Cambridge Reflection Models and Radiometry](https://www.cl.cam.ac.uk/teaching/1718/AdvGraph/01_Reflection_models.pdf) | Directional radiance, incidence cosine, and flux integration |
| [JPL Horizons Manual](https://ssd.jpl.nasa.gov/horizons/manual.html) | Independent celestial direction comparisons with consistent settings |

Observer positions, curvature formulas, the terrain coverage bound, the circular-segment fraction, and integrated metrics are derived above from the adopted geometric and physical assumptions. The sources supply data definitions and conventions needed to implement those derivations.

<a id="source-coverage"></a>

## 21. Coverage of the original material

The original algorithm document contained 13 main sections and 34 displayed formula blocks. The original derivation document contained 20 main sections and 154 displayed formula blocks; its text length was 33,084 characters. The tables below record where those topics and derivation blocks are represented in the merged document.

Definitions may appear in notation tables, related equations may share one aligned block, and example inputs may appear in the surrounding prose. Consequently, formula-block counts alone do not establish completeness. Fifteen intermediate blocks that had been shortened to prose or combined too aggressively have been made explicit again. The current document has 154 displayed blocks, including additional occultation, power, and uncertainty expressions beyond the original derivation; equal totals do not imply a one-to-one correspondence.

### 21.1. Algorithm document

| Original topic | Current section |
| --- | --- |
| Inputs and requested outputs | [2](#model), [16](#metrics) |
| Data sources, libraries, and matching lunar frames | [3](#data) |
| Surface model, ground elevation, and observer height | [4](#position) |
| Local east north up, azimuth, and elevation | [5](#basis), [6](#transform), [7](#angles) |
| Terrain horizon and exact spherical scan | [8](#horizon) |
| Sufficient terrain coverage | [9.1](#terrain) |
| Narrow ridges, interpolation, and missing data | [9.2](#terrain) |
| Sun and Earth vectors with SPICE | [10](#ephemeris) |
| Centre visibility, finite discs, and Earth occultation | [11](#solar-disc), [12](#eclipse), [13](#earth) |
| Event detection and refinement | [15](#events) |
| Durations, interruptions, and equivalent disc time | [16](#metrics) |
| Calculation order and repeated site or date scenarios | [17](#architecture) |
| Validation cases and convergence | [18](#validation) |

The original suggestion to divide the implementation into separate modules has been superseded by the chosen single-file implementation. The calculation responsibilities and order are retained in section 17. Original pseudocode is described as a workflow, not presented as an implemented data ingestion layer.

### 21.2. Derivation document

The first column numbers the displayed formula blocks in their original order in `2.md`, before it was merged and removed. It is an editorial coverage index rather than a symbolic equivalence proof.

| Original formula blocks | Mathematical content | Current location |
| --- | --- | --- |
| 001 | Coordinate definitions | [2](#model), [4.1](#position) |
| 002-009 | Spherical position and axis checks | [4](#position); [E002](#eq-002) to [E007](#eq-007) |
| 010-013 | Radial up and its numerical example | [4.3](#position), [5.1](#basis); [E008](#eq-008), [E013](#eq-013), [E014](#eq-014) |
| 014-021 | East derivative, norm, normalization, and reference meridians | [5.2](#basis) |
| 022-027 | North derivative, factored form, norm, and example | [5.3](#basis) |
| 028-036 | Lengths, orthogonality, and right-handed orientation | [5.4](#basis) |
| 037 | Terrain derivative and the distinction between normals | [5.5](#basis); [E034](#eq-034) |
| 038-045 | Local projections and both matrix directions | [6](#transform) |
| 046-053 | Observer position, ground elevation, and body-vector origin | [4.3](#position), [6.3](#transform) |
| 054-061 | Elevation, sine relation, and azimuth | [7.1 and 7.2](#angles) |
| 062-070 | Complete ENU numerical example | [7.3](#angles) |
| 071-076 | Terrain vectors, skyline maximum, and angular clearance | [6.3](#transform), [8.1](#horizon) |
| 077-081 | Great-circle scan and exact curvature geometry | [8.2 and 8.3](#horizon) |
| 082-090 | Small-angle curvature approximation and summit example | [8.4](#horizon) |
| 091-097 | Smooth-sphere tangent horizon and the zero-height limit | [8.5](#horizon) |
| 098-102 | Two-tangent terrain coverage bound and distance example | [9.1](#terrain) |
| 103-109 | Angular body size and full or partial disc visibility | [11.1 and 11.2](#solar-disc) |
| 110-125 | Circular strips, integration substitution, visible area, and fraction | [11.3](#solar-disc) |
| 126-131 | Directional masks, weighted area, equal-area sampling, and mask intersection | [11.4 and 11.5](#solar-disc), [12](#eclipse) |
| 132-135 | Panel parameters, projected area, and electrical power | [14](#power) |
| 136-145 | Transition equation, endpoint values, linear estimate, and event example | [15](#events) |
| 146-150 | State indicator, interval durations, and longest runs | [16.1 and 16.2](#metrics) |
| 151-154 | Equivalent disc time, energy, and simultaneous windows | [16.3 to 16.5](#metrics) |

All twenty original derivation topics are covered: coordinates, position, up, east, north, basis checks, transformations, observer-relative directions, angles and their example, the terrain horizon, exact and approximate curvature, a negative horizon, terrain extent, a finite solar disc, the visible-area integral, uneven-horizon sampling, panel power, transition times, and durations. The original concluding mathematical conditions and reading references are retained in sections 18.3 and 20.
