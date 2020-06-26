%% setup
number_x = 20;
number_y = 10;
n_objects = number_x*number_y; %# objects

SNRs = [0.25, 0.5,  0.75, 1:1:10, 15, 20 30 40 60 80 100];

pixel_spacing_x = 20;
pixel_spacing_y = pixel_spacing_x;

mic_pixels_x = (number_x+1)*pixel_spacing_x; %# pixels
mic_pixels_y = (number_y+1)*pixel_spacing_y; %# pixels

mic_pixelsize = 200;

pos_x = [pixel_spacing_x:pixel_spacing_x:number_x*pixel_spacing_x]*mic_pixelsize;
pos_y = [pixel_spacing_y:pixel_spacing_y:number_y*pixel_spacing_y]*mic_pixelsize;

pos_x = (pos_x - 0.5*mic_pixelsize); % pixel adjust
pos_y = (pos_y - 0.5*mic_pixelsize); % pixel adjust

n_frames = 1000;
%% load in data
% Use "import data"
% Import as Numeric Matrix

%% fit checker setup
columns_not_fitted = [1 2 3];
x_column = 2; %what column has x-pos in the return data
y_column = 3; %what column has y-pos in the return data
n_fits_per_frame = (number_x-size(columns_not_fitted,2))*number_y;
i_fit = 1; % row index

sigma_column = 4;

%% fit checker %% clear test
clear res_precision res_accuracy res_mean res_precision_imageJ
for i=1:number_x
    for j=1:number_y
    if ismember(i, columns_not_fitted)
        continue
    end
    fit_x = data((i-1-size(columns_not_fitted,2))*number_y+j:n_fits_per_frame:n_frames*n_fits_per_frame,x_column);
    fit_y = data((i-1-size(columns_not_fitted,2))*number_y+j:n_fits_per_frame:n_frames*n_fits_per_frame,y_column);
    fit_uncertainty = data((i-1-size(columns_not_fitted,2))*number_y+j:n_fits_per_frame:n_frames*n_fits_per_frame,9); % 8 for MLE, 9 for LS

    sigma = data((i-1-size(columns_not_fitted,2))*number_y+j:n_fits_per_frame:n_frames*n_fits_per_frame,sigma_column);
    sigma_mean = mean(sigma);
    res_sigma_precision(i,j) = sum((sigma - sigma_mean).^2)/(size(sigma,1)-1);
    res_sigma_accuracy(i,j) = sigma_mean - mic_pixelsize;

    
    res_precision_imageJ(i,j) = mean(fit_uncertainty);
    fit_x_mean = mean(fit_x);
    fit_y_mean = mean(fit_y);
    fit_x_std = sum((fit_x - fit_x_mean).^2)/(size(fit_x,1)-1);
    fit_y_std = sum((fit_y - fit_y_mean).^2)/(size(fit_y,1)-1);
    res_precision(i,j) = sqrt(fit_x_std^2 + fit_y_std^2);
    res_accuracy(i,j) = sqrt(sum(([pos_x(i) pos_y(j)] - [fit_x_mean fit_y_mean]).^2));
    end
end

res_mean_precision_imageJ = nanmean(res_precision_imageJ,2);
res_mean_precision = nanmean(res_precision,2);
res_mean_accuracy = nanmean(res_accuracy,2);
res_mean_sigma_precision = nanmean(res_sigma_precision,2);
res_mean_sigma_accuracy = nanmean(res_sigma_accuracy,2);
%% clear test
%clear res_precision res_accuracy res_mean