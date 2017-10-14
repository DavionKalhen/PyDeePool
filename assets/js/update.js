$( function()
{   $('#search').click( function(event) {
        event.preventDefault();
        jQuery.get( "/addr/" + $('#input').val() + "/", function( data ) {
            $( "#cardbody" ).html( data );
        });
    } );
});

window.setInterval(function(){
        if($('#input').val())
        {   jQuery.get( "/addr/" + $('#input').val() + "/", function( data ) {
                $( "#cardbody" ).html( data );
            });
        }

}, 30000);
  
