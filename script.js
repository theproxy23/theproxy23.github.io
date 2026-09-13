document.addEventListener('DOMContentLoaded', () => {
  const accountLink = document.querySelector('nav.links a[href="cuenta.html"]');
  if (!accountLink) {
    const navigation = document.querySelector('nav.links');
    if (navigation) {
      const link = document.createElement('a');
      link.href = 'cuenta.html';
      link.textContent = 'Cuenta';
      navigation.appendChild(link);
    }
  }

  const illus = document.getElementById('illus');
  if (illus && 'IntersectionObserver' in window) {
    const observer = new IntersectionObserver((entries) => {
      if (entries[0].isIntersecting) {
        illus.classList.add('drawn');
        observer.disconnect();
      }
    }, { threshold: 0.4 });
    observer.observe(illus);
  }

  const cube = document.getElementById('cube');
  const stage = document.getElementById('cube-stage');
  if (cube && stage) {
    let dragging = false;
    let lastX = 0;
    let lastY = 0;
    let rotX = -20;
    let rotY = -30;
    const start = (x, y) => { dragging = true; lastX = x; lastY = y; };
    const move = (x, y) => {
      if (!dragging) return;
      rotY += (x - lastX) * 0.5;
      rotX -= (y - lastY) * 0.5;
      cube.style.transform = `rotateX(${rotX}deg) rotateY(${rotY}deg)`;
      lastX = x;
      lastY = y;
    };
    const end = () => { dragging = false; };
    stage.addEventListener('mousedown', (event) => start(event.clientX, event.clientY));
    window.addEventListener('mousemove', (event) => move(event.clientX, event.clientY));
    window.addEventListener('mouseup', end);
    stage.addEventListener('touchstart', (event) => start(event.touches[0].clientX, event.touches[0].clientY), { passive: true });
    stage.addEventListener('touchmove', (event) => move(event.touches[0].clientX, event.touches[0].clientY), { passive: true });
    stage.addEventListener('touchend', end);
  }

  const orbit = document.getElementById('orbit');
  const playToggle = document.getElementById('play-toggle');
  if (orbit && playToggle) {
    playToggle.addEventListener('click', () => {
      const paused = orbit.classList.toggle('paused');
      playToggle.textContent = paused ? 'Reanudar' : 'Pausar';
    });
  }

  document.querySelectorAll('.ctab').forEach((button) => {
    button.addEventListener('click', () => {
      document.querySelectorAll('.ctab').forEach((item) => item.classList.remove('on'));
      document.querySelectorAll('.cpanel').forEach((panel) => panel.classList.remove('active'));
      button.classList.add('on');
      document.getElementById(`panel-${button.dataset.panel}`)?.classList.add('active');
    });
  });

  const contactForm = document.querySelector('.contact-form');
  const formStatus = document.querySelector('.form-status');
  const attachmentInput = document.getElementById('adjuntos');
  const fileList = document.getElementById('file-list');
  const selectedTeam = document.getElementById('selected-team');
  const serviceLabels = {
    diseno: 'equipo de diseño',
    ilustracion: 'equipo de ilustración',
    '3d': 'equipo 3D',
    animacion: 'equipo de animación'
  };
  const selectedService = new URLSearchParams(window.location.search).get('equipo');
  if (selectedTeam && serviceLabels[selectedService]) {
    selectedTeam.textContent = `Equipo seleccionado: ${serviceLabels[selectedService]}`;
    selectedTeam.classList.add('visible');
    const selectedInput = document.createElement('input');
    selectedInput.type = 'hidden';
    selectedInput.name = 'equipo';
    selectedInput.value = serviceLabels[selectedService];
    contactForm?.appendChild(selectedInput);
  }
  if (attachmentInput && fileList) {
    attachmentInput.addEventListener('change', () => {
      const files = Array.from(attachmentInput.files || []);
      fileList.textContent = files.length
        ? `Archivos seleccionados: ${files.map((file) => file.name).join(', ')}`
        : '';
    });
  }
  if (contactForm && formStatus) {
    contactForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      const submitButton = contactForm.querySelector('button[type="submit"]');
      submitButton.disabled = true;
      formStatus.textContent = 'Enviando tu consulta...';
      try {
        const response = await fetch(contactForm.action, {
          method: 'POST',
          body: new FormData(contactForm)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'No se pudo enviar la consulta.');
        formStatus.textContent = result.message;
        contactForm.reset();
        if (fileList) fileList.textContent = '';
      } catch (error) {
        formStatus.textContent = error.message || 'No se pudo enviar la consulta.';
      } finally {
        submitButton.disabled = false;
      }
    });
  }

  const reviewForm = document.getElementById('review-form');
  const reviewStatus = document.getElementById('review-status');
  const reviewList = document.getElementById('review-list');
  const portfolioForm = document.getElementById('portfolio-form');
  const portfolioStatus = document.getElementById('portfolio-status');
  const portfolioGrid = document.getElementById('portfolio-grid');

  const renderReviews = (reviews) => {
    if (!reviewList) return;
    reviewList.replaceChildren();
    if (!reviews.length) {
      reviewList.innerHTML = '<p class="empty-state">Todavía no hay opiniones publicadas.</p>';
      return;
    }
    reviews.forEach((review) => {
      const article = document.createElement('article');
      article.className = 'review-card';
      const title = document.createElement('h3');
      title.textContent = review.name;
      const rating = document.createElement('p');
      rating.className = 'review-rating';
      rating.textContent = `${'★'.repeat(review.rating)}${'☆'.repeat(5 - review.rating)}`;
      const comment = document.createElement('p');
      comment.textContent = review.comment;
      article.append(title, rating, comment);
      reviewList.appendChild(article);
    });
  };

  if (reviewList) {
    fetch('/api/reviews')
      .then((response) => response.json())
      .then((result) => renderReviews(result.reviews || []))
      .catch(() => {});
  }
  if (reviewForm && reviewStatus) {
    reviewForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      reviewStatus.textContent = 'Publicando tu opinión...';
      try {
        const response = await fetch('/api/review', { method: 'POST', body: new URLSearchParams(new FormData(reviewForm)) });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'No se pudo publicar la opinión.');
        reviewStatus.textContent = result.message;
        reviewForm.reset();
        const reviewsResponse = await fetch('/api/reviews');
        renderReviews((await reviewsResponse.json()).reviews || []);
      } catch (error) {
        reviewStatus.textContent = error.message || 'No se pudo publicar la opinión.';
      }
    });
  }

  const renderPortfolio = (items) => {
    if (!portfolioGrid) return;
    portfolioGrid.replaceChildren();
    items.forEach((item) => {
      item.images.forEach((image) => {
        const figure = document.createElement('figure');
        figure.className = 'portfolio-card';
        const imageElement = document.createElement('img');
        imageElement.src = image.url;
        imageElement.alt = item.title;
        const caption = document.createElement('figcaption');
        caption.textContent = item.title;
        figure.append(imageElement, caption);
        portfolioGrid.appendChild(figure);
      });
    });
  };

  if (portfolioGrid) {
    fetch('/api/portfolio')
      .then((response) => response.json())
      .then((result) => renderPortfolio(result.items || []))
      .catch(() => {});
  }
  if (portfolioForm && portfolioStatus) {
    portfolioForm.addEventListener('submit', async (event) => {
      event.preventDefault();
      portfolioStatus.textContent = 'Subiendo imágenes...';
      try {
        const response = await fetch('/api/portfolio', {
          method: 'POST',
          headers: { 'X-Admin-Token': portfolioForm.elements.token.value },
          body: new FormData(portfolioForm)
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'No se pudo subir el portafolio.');
        portfolioStatus.textContent = result.message;
        portfolioForm.reset();
        const portfolioResponse = await fetch('/api/portfolio');
        renderPortfolio((await portfolioResponse.json()).items || []);
      } catch (error) {
        portfolioStatus.textContent = error.message || 'No se pudo subir el portafolio.';
      }
    });
  }

  const loginForm = document.getElementById('login-form');
  const registerForm = document.getElementById('register-form');
  const loginStatus = document.getElementById('login-status');
  const registerStatus = document.getElementById('register-status');
  const sessionPanel = document.getElementById('session-panel');
  const roleSelect = document.getElementById('register-role');
  const adminCodeField = document.querySelector('.admin-code-field');

  const submitAccountForm = async (form, status, endpoint) => {
    status.textContent = 'Procesando...';
    try {
      const response = await fetch(endpoint, { method: 'POST', body: new URLSearchParams(new FormData(form)) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || 'No se pudo completar la operación.');
      status.textContent = result.message;
      form.reset();
      if (endpoint === '/api/login') window.location.reload();
    } catch (error) {
      status.textContent = error.message || 'No se pudo completar la operación.';
    }
  };
  if (roleSelect && adminCodeField) {
    const toggleAdminCode = () => {
      const isAdmin = roleSelect.value === 'admin';
      adminCodeField.hidden = !isAdmin;
      adminCodeField.querySelector('input').required = isAdmin;
    };
    roleSelect.addEventListener('change', toggleAdminCode);
    toggleAdminCode();
  }
  loginForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    submitAccountForm(loginForm, loginStatus, '/api/login');
  });
  registerForm?.addEventListener('submit', (event) => {
    event.preventDefault();
    submitAccountForm(registerForm, registerStatus, '/api/register');
  });
  if (sessionPanel) {
    fetch('/api/me')
      .then((response) => response.ok ? response.json() : null)
      .then((result) => {
        if (!result) {
          sessionPanel.innerHTML = '<p>No has iniciado sesión.</p>';
          return;
        }
        sessionPanel.replaceChildren();
        const sessionText = document.createElement('p');
        sessionText.textContent = `Sesión activa como ${result.user.name} · ${result.user.role === 'admin' ? 'Administrador' : 'Cliente'}`;
        const logoutButton = document.createElement('button');
        logoutButton.className = 'btn ghost';
        logoutButton.type = 'button';
        logoutButton.textContent = 'Cerrar sesión';
        sessionPanel.append(sessionText, logoutButton);
        logoutButton.addEventListener('click', async () => {
          await fetch('/api/logout', { method: 'POST' });
          window.location.reload();
        });
      })
      .catch(() => { sessionPanel.innerHTML = '<p>No se pudo comprobar la sesión.</p>'; });
  }

  const serviceCards = document.querySelectorAll('.service-card');
  const serviceButtons = document.querySelectorAll('.service-select');
  const selectionNote = document.getElementById('selection-note');
  const contactSelected = document.getElementById('contact-selected');
  if (serviceCards.length && selectionNote && contactSelected) {
    const labels = {
      diseno: 'equipo de diseño',
      ilustracion: 'equipo de ilustración',
      '3d': 'equipo 3D',
      animacion: 'equipo de animación'
    };
    const selectService = (service) => {
      serviceCards.forEach((card) => card.classList.toggle('selected', card.dataset.service === service));
      serviceButtons.forEach((button) => {
        button.textContent = button.dataset.service === service ? 'Equipo elegido' : 'Elegir este equipo';
      });
      selectionNote.classList.add('selected');
      selectionNote.textContent = `Has elegido el ${labels[service]}. Continúa para contarnos tu proyecto.`;
      contactSelected.href = `contacto.html?equipo=${encodeURIComponent(service)}`;
    };
    const requestedService = new URLSearchParams(window.location.search).get('equipo');
    if (labels[requestedService]) selectService(requestedService);
    serviceButtons.forEach((button) => button.addEventListener('click', () => selectService(button.dataset.service)));
  }
});
