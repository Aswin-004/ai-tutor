(function () {
    let scene, camera, renderer, particles, animationId;
    let running = false;

    function startAuthBG() {
        if (running) return;
        running = true;

        const container = document.getElementById('three-auth-bg');
        if (!container) return;

        scene = new THREE.Scene();

        camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
        camera.position.z = 5;

        renderer = new THREE.WebGLRenderer({ alpha: true, antialias: false });
        renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
        renderer.setSize(window.innerWidth, window.innerHeight);
        container.appendChild(renderer.domElement);

        const count = window.innerWidth < 768 ? 40 : 80;
        const geometry = new THREE.BufferGeometry();
        const positions = new Float32Array(count * 3);
        for (let i = 0; i < count * 3; i++) {
            positions[i] = (Math.random() - 0.5) * 10;
        }
        geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));

        const material = new THREE.PointsMaterial({
            color: 0x88ccff,
            size: 0.05,
            transparent: true,
            opacity: 0.7,
        });

        particles = new THREE.Points(geometry, material);
        scene.add(particles);

        animate();
    }

    function animate() {
        if (!running) return;
        animationId = requestAnimationFrame(animate);
        particles.rotation.y += 0.001;
        particles.rotation.x += 0.0005;
        renderer.render(scene, camera);
    }

    function stopAuthBG() {
        running = false;
        if (animationId) cancelAnimationFrame(animationId);
        if (renderer) {
            renderer.dispose();
            renderer.domElement.remove();
        }
        scene = null;
        camera = null;
        renderer = null;
        particles = null;
    }

    window.startAuthBG = startAuthBG;
    window.stopAuthBG = stopAuthBG;

    // Auto-start if auth section is the active view when this script loads
    if (document.getElementById('auth-section') &&
        document.getElementById('auth-section').classList.contains('active')) {
        startAuthBG();
    }
})();
