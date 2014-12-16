        // Ajax history
        // set inital state to accessed page
        $.History.go('/');
        // create funtion to update page after each state change
        var updateNav = function(state){
            // Make clicked menu active
          $('a[href="#'+state+'"]').parent().addClass('active').siblings('.active').removeClass('active');
            // unhide selected sections and hide all others
          };
        $.History.bind(function(state){
        });
        $.History.bind('/', function(state){
          updateNav(state);
          $('#the-archive').removeClass('hidden');
        });
        $.History.bind('/create-article', function(state){
          updateNav(state);
          $('#the-archive').addClass('hidden');
        });
        $.History.bind('/create-article2', function(state){
          updateNav(state);
          $('#the-archive').addClass('hidden');
        });
